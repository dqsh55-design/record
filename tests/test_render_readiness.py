"""Free runtime contracts; all success documents below are synthetic fixtures."""
import copy
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
sys.path.insert(0,str(Path(__file__).resolve().parent))
from realtime_fixtures import Pages,blue_page
from server.public import create_public_app,PAGES_ORIGIN,DAILY_FETCH_LIMIT
from server.source_policy import SourcePolicy
from server.search import OfficialTransport,SourceError
ROOT=Path(__file__).resolve().parents[1]
NOW=1793059200

def approved(clock):
    # Test evidence only. Never written to the production policy document.
    entry={'status':'approved','scope':'public-automated-release-metadata','permissionEvidenceUrl':'https://permission.example.test/fixture','reviewedAt':datetime.fromtimestamp(NOW,timezone.utc).isoformat(),'validUntil':datetime.fromtimestamp(NOW+2*86400,timezone.utc).isoformat()}
    return SourcePolicy({'version':1,'hosts':{'www.bluenote.com':entry,'wmg.jp':copy.deepcopy(entry)}},clock)

class RenderReadiness(unittest.TestCase):
    def app(self,clock=lambda:NOW,policy=None,factory=OfficialTransport,path=':memory:'):
        app=create_public_app(cache_path=path,clock=clock,policy=policy,transport_factory=factory)
        self.addCleanup(app.service.cache.close);return app

    def call(self,app,name='Willie Nelson',origin=PAGES_ORIGIN,path='/api/search',query=None,method='GET'):
        response={};env={'REQUEST_METHOD':method,'PATH_INFO':path,'QUERY_STRING':query if query is not None else urlencode({'q':name})}
        if origin is not None:env['HTTP_ORIGIN']=origin
        raw=b''.join(app(env,lambda s,h:response.update(status=s,headers=dict(h))));response['body']=json.loads(raw);return response

    def test_production_policy_permits_no_unclear_hosts(self):
        policy=SourcePolicy.load()
        for host in policy.document['hosts']:self.assertFalse(policy.permits(host))
        self.assertFalse(policy.permits('evil.test'))

    def test_permission_requires_scope_evidence_and_short_expiry(self):
        policy=approved(lambda:NOW);self.assertTrue(policy.permits('wmg.jp'))
        for key,value in [('scope','personal'),('permissionEvidenceUrl','http://unsafe.test'),('reviewedAt','bad'),('status','review_required'),('validUntil','2099-01-01T00:00:00Z')]:
            bad=copy.deepcopy(policy.document);bad['hosts']['wmg.jp'][key]=value
            self.assertFalse(SourcePolicy(bad,lambda:NOW).permits('wmg.jp'))
        self.assertFalse(approved(lambda:NOW+2*86400).permits('wmg.jp'))

    def test_unknown_sources_never_request_even_robots(self):
        transport=OfficialTransport({'wmg.jp'})
        with patch('server.search.build_opener') as network:
            with self.assertRaises(SourceError) as error:transport({'host':'wmg.jp','url':'https://wmg.jp/artistlist'})
            self.assertEqual(error.exception.kind,'policy_restricted');network.assert_not_called()

    def test_unknown_willie_japanese_english_http_reports_policy_not_no_release(self):
        app=self.app()
        with patch('server.search.build_opener') as network:
            for name in ['Willie Nelson','ウィリー・ネルソン']:
                response=self.call(app,name);self.assertTrue(response['status'].startswith('200'))
                self.assertEqual(response['body']['status'],'policy_restricted');self.assertEqual(response['body']['artist']['albums'],[])
            network.assert_not_called()

    def test_new_ephemeral_store_cannot_mint_same_day_budget(self):
        now=[NOW];app=self.app(clock=lambda:now[0]);reserve=app.service.fetch.reserve
        self.assertFalse(reserve());now[0]=app.not_before
        self.assertTrue(all(reserve() for _ in range(DAILY_FETCH_LIMIT)));self.assertFalse(reserve())
        replacement=self.app(clock=lambda:now[0]);self.assertFalse(replacement.service.fetch.reserve())

    def test_worker_restart_with_same_store_retains_exhausted_budget(self):
        now=[NOW]
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/'cache.sqlite3');app=self.app(clock=lambda:now[0],path=path);now[0]=app.not_before
            self.assertTrue(all(app.service.fetch.reserve() for _ in range(DAILY_FETCH_LIMIT)))
            restarted=self.app(clock=lambda:now[0],path=path);self.assertFalse(restarted.service.fetch.reserve())

    def test_originless_and_hostile_requests_do_not_search(self):
        app=self.app()
        with patch.object(app.service,'search') as search:
            for origin in [None,'null','https://evil.test','https://dqsh55-design.github.io.evil.test']:
                self.assertTrue(self.call(app,origin=origin)['status'].startswith('403'))
            search.assert_not_called()

    def test_only_health_and_search_are_served(self):
        app=self.app()
        self.assertEqual(self.call(app,path='/health',origin=None)['body']['status'],'ok')
        for path in ['/','/record/','/server/public.py','/.git/config','/data/official-access-policy.json']:
            self.assertTrue(self.call(app,path=path)['status'].startswith('404'))

    def test_public_rate_limit_and_retry_after(self):
        app=self.app()
        for _ in range(10):self.assertTrue(self.call(app)['status'].startswith('200'))
        limited=self.call(app);self.assertTrue(limited['status'].startswith('429'));self.assertEqual(limited['headers']['Retry-After'],'60')

    def fixture_app(self):
        now=[NOW];pages=Pages();pages.pages['https://www.bluenote.com/artists/']+='<h5 class="post-name"><a href="/artist/willie-nelson/">Willie Nelson</a></h5>'
        pages.pages['https://www.bluenote.com/artist/willie-nelson/']=blue_page('Willie Nelson','willie-nelson',['American Classic'])
        def factory(hosts,clock,reserve,access_policy):
            def fetch(source):
                if not access_policy.permits(source['host']):raise SourceError('policy_restricted')
                if not reserve():raise SourceError('budget_exhausted')
                return pages(source)
            return fetch
        policy=approved(lambda:now[0]);app=self.app(clock=lambda:now[0],policy=policy,factory=factory);now[0]=app.not_before
        return app,pages,policy,now

    def test_synthetic_willie_pipeline_preserves_proof_and_cached_result(self):
        app,pages,policy,now=self.fixture_app();first=self.call(app)['body'];album=first['artist']['albums'][0]
        self.assertEqual((album['title'],album['year'],album['label']),('American Classic','2002','Blue Note Records'))
        self.assertEqual(album['sourceUrl'],'https://www.bluenote.com/artist/willie-nelson/');self.assertNotIn('listeningLink',album)
        count=len(pages.calls);second=self.call(app,query='q=Willie+Nelson&refresh=1')['body']
        self.assertTrue(second['cache']['hit']);self.assertEqual(len(pages.calls),count)

    def test_synthetic_japanese_willie_discovery_without_registration(self):
        app,pages,policy,now=self.fixture_app()
        pages.pages['https://wmg.jp/artistlist']='<a href="/WillieNelson">ウィリー・ネルソン</a><a href="/WillieNelson">Willie Nelson</a>'
        pages.pages['https://wmg.jp/WillieNelson/discography/album']='<p class="x_artistName">ウィリー・ネルソン</p><a href="/WillieNelson/discography/3355"><h3>Fixture Atlantic Album</h3><p class="x_releaseInfo">2006.08.23 発売</p><span>ALBUM</span></a>'
        result=self.call(app,'ウィリー・ネルソン')['body']
        self.assertEqual(result['artist']['albums'][0]['label'],'Warner Music Japan')
        self.assertEqual(result['artist']['albums'][0]['year'],'2006')
        before=len(pages.calls);self.assertTrue(self.call(app,'Willie Nelson')['body']['cache']['hit']);self.assertEqual(len(pages.calls),before)

    def test_revoked_permission_cannot_leak_previously_cached_albums(self):
        app,pages,policy,now=self.fixture_app();self.assertTrue(self.call(app)['body']['artist']['albums'])
        policy.document['hosts']['www.bluenote.com']['status']='review_required'
        result=self.call(app)['body'];self.assertEqual(result['artist']['albums'],[]);self.assertEqual(result['status'],'policy_restricted')

    def test_native_free_blueprint_has_no_db_secrets_or_auto_deploy(self):
        text=(ROOT/'render.yaml').read_text()
        for value in ['plan: free','runtime: python','numInstances: 1','autoDeployTrigger: off','--workers 1','--threads 4','server.public:create_public_app()']:
            self.assertIn(value,text)
        for value in ['sync: false','DATABASE_URL','databases:','disk:','plan: starter']:self.assertNotIn(value,text)
        self.assertEqual((ROOT/'server/requirements-free.txt').read_text().strip(),'gunicorn==26.2.0')

    def test_database_configuration_is_rejected(self):
        with patch.dict(os.environ,{'RECORD_DATABASE_URL':'postgres://should-not-connect'}):
            with self.assertRaises(ValueError):create_public_app()

if __name__=='__main__':unittest.main()
