"""Single-process, database-free Render preparation. No deployment is performed."""
import json
import os
import time
from urllib.parse import urlsplit
from .app import create_app
from .search import OfficialSearch, OfficialTransport, ROOT
from .source_policy import SourcePolicy

PAGES_ORIGIN='https://dqsh55-design.github.io'
DAILY_FETCH_LIMIT=100


def create_public_app(cache_path=None,clock=time.time,policy=None,transport_factory=OfficialTransport):
    # Never use an old credential-bearing DB configuration for this free option.
    if os.environ.get('RECORD_DATABASE_URL'):
        raise ValueError('This free preparation uses no external database')
    policy=policy or SourcePolicy.load(clock)
    service=OfficialSearch(json.loads((ROOT/'data/official-realtime.json').read_text()),cache_path or os.environ.get('RECORD_CACHE_PATH','/tmp/record-official-cache.sqlite3'),clock=clock)
    cache=service.cache
    # A lost ephemeral ledger must not renew the same day's outbound allowance.
    # Single instance + one Gunicorn worker are required; a fresh store waits until
    # the next UTC day, so restarts cannot repeatedly mint today's fetch budget.
    with cache.transaction() as db:
        db.execute('CREATE TABLE IF NOT EXISTS launch_guard (id INTEGER PRIMARY KEY, not_before REAL NOT NULL)')
        db.execute('INSERT OR IGNORE INTO launch_guard VALUES (1,?)',((int(clock())//86400+1)*86400,))
        not_before=db.execute('SELECT not_before FROM launch_guard WHERE id=1').fetchone()[0]
    def reserve():
        return clock()>=not_before and cache.reserve_fetch(DAILY_FETCH_LIMIT)
    hosts={h for p in service.config['providers'].values() for h in p['hosts']}
    service.fetch=transport_factory(hosts,clock=clock,reserve=reserve,access_policy=policy)
    base=create_app(service,allowed_origins=[PAGES_ORIGIN],request_limit=10)
    def application(environ,start_response):
        path=environ.get('PATH_INFO','')
        status=None;body=None
        if path not in {'/health','/api/search'}:
            status='404 Not Found';body={'status':'not_found'}
        elif path=='/api/search' and environ.get('HTTP_ORIGIN')!=PAGES_ORIGIN:
            status='403 Forbidden';body={'status':'origin_not_allowed'}
        if status:
            data=json.dumps(body,ensure_ascii=False).encode()
            headers=[('Content-Type','application/json; charset=utf-8'),('Content-Length',str(len(data))),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('Vary','Origin')]
            if environ.get('HTTP_ORIGIN')==PAGES_ORIGIN:headers.append(('Access-Control-Allow-Origin',PAGES_ORIGIN))
            start_response(status,headers);return [data]
        return base(environ,start_response)
    # Re-check permissions even when the existing service returns cached evidence.
    search=service.search
    def permitted_search(query,refresh=False):
        result=search(query,refresh=False)
        albums=result['artist']['albums'];allowed=[a for a in albums if policy.permits(urlsplit(a['sourceUrl']).hostname)]
        if len(allowed)!=len(albums):
            result['artist']['albums']=allowed
            result['status']='partial' if allowed else 'policy_restricted'
            result['sources'].append({'id':'cache-permission-check','status':'policy_restricted','code':'permission_revoked_or_expired'})
        return result
    service.search=permitted_search
    application.service=service
    application.not_before=not_before
    return application
