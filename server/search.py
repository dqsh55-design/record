"""On-demand official-only discovery, release verification and persistent cache."""
from concurrent.futures import ThreadPoolExecutor, Future
import copy
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import generate_official_catalog as rules
from official_discography import Links, safe_url


class SourceError(Exception):
    def __init__(self, kind, code=''):
        super().__init__(kind)
        self.kind, self.code = kind, str(code)


class OfficialTransport:
    """Only approved origins; no cross-host redirect, credentials or restriction bypass."""
    def __init__(self, hosts, timeout=12, clock=time.time):
        self.hosts, self.timeout, self.clock = set(hosts), timeout, clock
        self.blocked = {}
        self.pages = {}
        self.lock = threading.Lock()

    def __call__(self, source):
        url, host = source['url'], source['host']
        if host not in self.hosts or not safe_url(url, host):
            raise SourceError('unsafe_source')
        with self.lock:
            if self.blocked.get(host, 0) > self.clock():
                raise SourceError('blocked', 'cooldown')
            cached = self.pages.get(url)
            if cached and cached[0] > self.clock():
                return cached[1]
        class Redirects(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, target):
                if not safe_url(target, host):
                    raise SourceError('unsafe_redirect')
                return super().redirect_request(req, fp, code, msg, headers, target)
        try:
            with build_opener(Redirects()).open(Request(url, headers={'User-Agent':'RECORD-OfficialSearch/1.0'}), timeout=self.timeout) as response:
                if 'html' not in response.headers.get('Content-Type','').casefold():
                    raise SourceError('unsupported_format')
                data = response.read(5_000_001)
                if len(data) > 5_000_000:
                    raise SourceError('response_too_large')
                encoding = (response.headers.get_content_charset() or 'utf-8').casefold()
                if encoding not in {'utf-8','shift_jis','euc-jp','iso-8859-1'}:
                    raise SourceError('unsupported_encoding')
                html = data.decode(encoding)
        except HTTPError as error:
            if error.code in {401,403,429}:
                with self.lock:
                    self.blocked[host] = self.clock()+180
                raise SourceError('blocked',error.code) from None
            raise SourceError('not_found' if error.code == 404 else 'fetch_error',error.code) from None
        except (TimeoutError, URLError, UnicodeError):
            raise SourceError('fetch_error','network_or_encoding') from None
        if re.search(r'<title[^>]*>\s*(?:Just a moment|Access Denied|Attention Required|Forbidden)',html,re.I):
            with self.lock:
                self.blocked[host]=self.clock()+180
            raise SourceError('blocked','challenge_page')
        with self.lock:
            if len(self.pages) >= 128:
                self.pages.pop(next(iter(self.pages)))
            self.pages[url] = (self.clock()+60, html)
        return html


def artist_music_html(source, html, fetch, today):
    """Official artist music pages with explicitly labelled release-date fields."""
    structured, held = rules.jsonld(source, html, today)
    if structured:
        return structured, held, []
    urls = []
    for block in re.findall(r'<div\b[^>]*class="views-field-title-music"[^>]*>(.*?)</div>', html, re.S):
        for href in re.findall(r'<a\b[^>]*href=[\'"]([^\'"]+)[\"]', block):
            url = urljoin(source['url'], href)
            if safe_url(url, source['host']) and re.fullmatch(source['releasePath'], urlsplit(url).path) and url not in urls:
                urls.append(url)
    def inspect(url):
        report = dict(id=source['id']+':detail', url=url, status='unconfirmed')
        try:
            page = fetch(dict(source, url=url))
            def field(tag, name):
                match = re.search('<'+tag+r'\b[^>]*class="'+name+r'"[^>]*>(.*?)</'+tag+'>', page, re.S)
                return rules.text(match[1]) if match else ''
            name, title, released = field('div', 'music-artist'), field('h1', 'music-title'), field('div', 'music-release-date')
            if rules.norm(name) not in rules.names(source) or not title or 'id="music-tracks"' not in page or 'Experience Hendrix' not in rules.text(page):
                return None, report
            # Article publication timestamps are deliberately never used as release dates.
            release_date = None
            for pattern in ['%B %d, %Y', '%b %d, %Y', '%Y-%m-%d']:
                try:
                    release_date = datetime.strptime(released, pattern).date()
                    break
                except ValueError:
                    pass
            description = ''
            for attrs in re.findall(r'<meta\b([^>]+)>', page, re.S):
                parser = MetaAttributes(); parser.feed('<meta '+attrs+'>')
                if parser.attrs.get('property') == 'og:description':
                    description = parser.attrs.get('content', '')
            if not release_date or release_date > today or not re.search(r'(?i)(?:\balbum\b|\bvinyl\b|\b\d*CD\b|\bLP\b)', description):
                return None, report
            item = dict(title=title, url=url, label='Experience Hendrix', listedReleaseDate=release_date.isoformat(), detailSha256=hashlib.sha256(page.encode()).hexdigest())
            report.update(status='ok', verified=1)
            return item, report
        except SourceError as error:
            report.update(status=error.kind, code=error.code)
            return None, report
        except Exception:
            report.update(status='fetch_error', code='source_format')
            return None, report
    entries, diagnostics = [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for item, report in pool.map(inspect, urls[:6]):
            diagnostics.append(report)
            if item: entries.append(item)
            else: held += 1
    return entries, held, diagnostics


class MetaAttributes(rules.HTMLParser):
    def __init__(self):
        super().__init__()
        self.attrs = {}

    def handle_starttag(self, tag, attrs):
        if tag == 'meta': self.attrs = dict(attrs)


def valid_album(album, artist, config, now):
    try:
        proof=album['generationProof']
        provider=config['providers'][proof['provider']]
        url=urlsplit(album['sourceUrl'])
        return (album['official'] is True and album['scope']=='work' and bool(album['title'].strip()) and
                rules.good_label(album['label']) and bool(album['reviewNote'].strip()) and
                album['verificationMethod']==rules.RULE_VERSION and proof['artistId']==artist['id'] and
                proof['sourceUrl']==album['sourceUrl'] and proof['rule']==provider['adapter'] and
                isinstance(proof['sourceId'],str) and bool(proof['sourceId'].strip()) and
                album['checkedAt']==datetime.fromtimestamp(album['verifiedAtUnix'],timezone.utc).date().isoformat() and
                bool(re.fullmatch(r'[a-f0-9]{64}',proof['sourceSha256'])) and
                url.hostname in provider['hosts'] and safe_url(album['sourceUrl'],url.hostname) and
                0 <= now-album['verifiedAtUnix'] < config['cacheSeconds'] and
                album['validUntilUnix'] > now and
                (rules.past_date(proof['listedReleaseDate'],datetime.fromtimestamp(now,timezone.utc).date()) if proof.get('listedReleaseDate') else
                 bool(re.fullmatch(r'\d{4}',proof.get('listedReleaseYear',''))) and 1900 <= int(proof['listedReleaseYear']) < datetime.fromtimestamp(now,timezone.utc).date().year))
    except (KeyError,TypeError,ValueError,AttributeError):
        return False


class VerifiedCache:
    def __init__(self, path, config, clock=time.time):
        self.config, self.clock = config, clock
        if str(path)!=':memory:': Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(str(path),check_same_thread=False)
        self.lock=threading.Lock()
        with self.db:
            self.db.execute('CREATE TABLE IF NOT EXISTS verified (artist_id TEXT PRIMARY KEY, body TEXT NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS queries (query_key TEXT PRIMARY KEY, artist_id TEXT NOT NULL)')

    def get(self, query):
        with self.lock:
            row=self.db.execute('SELECT body FROM verified JOIN queries USING(artist_id) WHERE query_key=?',(rules.norm(query),)).fetchone()
        if not row:
            return None
        try:
            body=json.loads(row[0])
            body['artist']['albums']=[a for a in body['artist']['albums'] if valid_album(a,body['artist'],self.config,self.clock())]
            if not body['artist']['albums']:
                return None
            body['cache']={'hit':True,'refreshFailed':False}
            return body
        except (ValueError,KeyError,TypeError):
            return None

    def save(self, query, body):
        artist=body['artist']
        if not artist['albums'] or not all(valid_album(a,artist,self.config,self.clock()) for a in artist['albums']):
            raise ValueError('only verified, unexpired works may be saved')
        with self.lock, self.db:
            row=self.db.execute('SELECT body FROM verified WHERE artist_id=?',(artist['id'],)).fetchone()
            merged={}
            if row:
                try:
                    old=json.loads(row[0])
                    merged={rules.norm(rules.work_title(a['title'])):a for a in old['artist']['albums'] if valid_album(a,artist,self.config,self.clock())}
                except (ValueError,TypeError,KeyError):
                    pass
            incoming={rules.norm(rules.work_title(a['title'])):a for a in artist['albums']}
            reused=bool(set(merged)-set(incoming))
            merged.update(incoming)
            saved=copy.deepcopy(body)
            if reused: saved['cache']=dict(hit=True,mixed=True,refreshFailed=False)
            saved['artist']['albums']=list(merged.values())
            self.db.execute('INSERT OR REPLACE INTO verified VALUES (?,?)',(artist['id'],json.dumps(saved,ensure_ascii=False)))
            for value in [query,artist['name'],*artist.get('aliases',[])]:
                self.db.execute('INSERT OR REPLACE INTO queries VALUES (?,?)',(rules.norm(value),artist['id']))
        return saved

    def close(self):
        self.db.close()


class OfficialSearch:
    def __init__(self, config, cache_path, fetch=None, clock=time.time):
        self.config, self.clock = config, clock
        hosts={h for p in config['providers'].values() for h in p['hosts']}
        self.fetch=fetch or OfficialTransport(hosts,clock=clock)
        self.cache=VerifiedCache(cache_path,config,clock)
        self.lock=threading.Lock()
        self.pending={}
        self.capacity=threading.BoundedSemaphore(4)

    def search(self, query, refresh=False):
        if not isinstance(query,str) or not query.strip() or len(query)>120 or not any(c.isalnum() for c in query) or any(ord(c)<32 for c in query) or '://' in query:
            raise ValueError('invalid artist query')
        query=query.strip()
        previous=self.cache.get(query)
        if previous and not refresh:
            return previous
        key=rules.norm(query)
        with self.lock:
            owner=key not in self.pending
            future=self.pending.setdefault(key,Future())
        if not owner:
            return copy.deepcopy(future.result(timeout=55))
        try:
            if not self.capacity.acquire(blocking=False):
                raise SourceError('busy')
            try:
                result=self._search(query)
            finally:
                self.capacity.release()
            if result['artist']['albums']:
                result=self.cache.save(query,result)
            elif previous:
                previous['status']='partial'
                previous['sources']=result['sources']
                previous['cache']['refreshFailed']=True
                result=previous
            future.set_result(result)
            return copy.deepcopy(result)
        except Exception as error:
            future.set_exception(error)
            # Retrieve the exception even if there were no waiting duplicate requests.
            future.exception()
            raise
        finally:
            with self.lock:
                self.pending.pop(key,None)

    def _directory(self, directory, identity):
        result=dict(id=directory['id'],url=directory['url'],status='ok')
        sources=[]
        try:
            provider=self.config['providers'][directory['provider']]
            if directory['host'] not in provider['hosts'] or not safe_url(directory['url'],directory['host']):
                raise SourceError('unsafe_source')
            html=self.fetch(directory)
            matches=[]
            if directory['kind']=='bluenote':
                for heading in re.findall(r'<h5\b[^>]*class="post-name"[^>]*>(.*?)</h5>',html,re.S):
                    matches.extend(re.findall(r'<a\b[^>]*href=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</a>',heading,re.S))
            else:
                parser=Links();parser.feed(html);matches=parser.links
            candidates={}
            aliases={rules.norm(n) for n in [identity['name'],*identity.get('aliases',[])]}
            valid_count=0
            for href,title in matches:
                url=urljoin(directory['url'],href)
                if not safe_url(url,directory['host']) or not re.fullmatch(directory['artistPath'],urlsplit(url).path):
                    continue
                valid_count+=1
                title=rules.text(title)
                variants=[title,*[x.strip() for x in title.split(' / ')]]
                if not any(rules.norm(v) in aliases for v in variants):
                    continue
                candidates[url]=title
            if not valid_count:
                raise SourceError('unsupported_format')
            for url,title in candidates.items():
                if len(sources)>=2:break
                artist=copy.deepcopy(identity)
                artist['aliases']=list(dict.fromkeys([*artist.get('aliases',[]),*variants]))
                if directory['kind']=='bluenote':
                    page=url
                    path=re.escape(urlsplit(url).path.rstrip('/'))+'/?'
                else:
                    page=url.rstrip('/')+'/discography'
                    path=re.escape(urlsplit(url).path.rstrip('/'))+r'/discography/[^/]+/?'
                sources.append(dict(id=directory['provider']+':'+urlsplit(url).path.strip('/'),provider=directory['provider'],artist=artist,host=directory['host'],url=page,releasePath=path))
            result['matches']=len(sources)
        except SourceError as error:
            result.update(status=error.kind,code=error.code)
        except Exception:
            result.update(status='fetch_error',code='source_format')
        return sources,result

    def _albums(self, source):
        diagnostic=dict(id=source['id'],url=source['url'],status='ok')
        entries=[]
        try:
            provider=self.config['providers'][source['provider']]
            if source['host'] not in provider['hosts'] or not safe_url(source['url'],source['host']):
                raise SourceError('unsafe_source')
            html=self.fetch(source)
            # Reuse exactly the same bounded, issuer/artist/release-aware adapters.
            if provider['adapter']=='artist-music-html-v1':
                items,held,details=artist_music_html(source,html,self.fetch,datetime.fromtimestamp(self.clock(),timezone.utc).date())
                diagnostic['detailSources']=details
            else:
                items,held=rules.ADAPTERS[provider['adapter']](source,html,datetime.fromtimestamp(self.clock(),timezone.utc).date())
            digest=hashlib.sha256(html.encode()).hexdigest()
            now=self.clock()
            for item in items:
                title=rules.work_title(item['title'])
                label=provider.get('label') or item.get('label')
                if not title or not rules.good_label(label):continue
                proof=dict(rule=provider['adapter'],provider=source['provider'],sourceId=source['id'],artistId=source['artist']['id'],sourceUrl=item['url'],sourceSha256=item.get('detailSha256',digest))
                proof.update({k:v for k,v in item.items() if k.startswith('listedRelease')})
                identity=hashlib.sha256((source['artist']['id']+'\n'+rules.norm(title)).encode()).hexdigest()[:24]
                album=dict(id='generated:'+identity,title=title,year=None,label=label,official=True,scope='work',sourceUrl=item['url'],sourceName=provider['name'],checkedAt=datetime.fromtimestamp(now,timezone.utc).date().isoformat(),reviewNote='公式発行元のアルバム区分・本人名義・発売済み日付を検索時に確認。初回発売年・配信先は未確認。',verificationMethod=rules.RULE_VERSION,generationProof=proof,verifiedAtUnix=now,validUntilUnix=now+self.config['cacheSeconds'])
                if valid_album(album,source['artist'],self.config,now):entries.append(album)
            diagnostic.update(status='ok' if entries else 'unconfirmed',verified=len(entries),held=held)
        except SourceError as error:
            diagnostic.update(status=error.kind,code=error.code)
        except Exception:
            diagnostic.update(status='fetch_error',code='source_format')
        return entries,diagnostic

    def _search(self, query):
        identity=next((copy.deepcopy(a) for a in self.config['identities'] if any(rules.norm(query)==rules.norm(n) for n in [a['name'],*a.get('aliases',[])])),None)
        if identity is None:
            identity=dict(id='record:query:'+hashlib.sha256(rules.norm(query).encode()).hexdigest()[:20],name=query,aliases=[])
        anchors=identity.pop('sources',[])
        # The trust registry contains identity/official origins, never album entries.
        sources=[dict(s,artist=identity) for s in anchors]
        diagnostics=[]
        with ThreadPoolExecutor(max_workers=3) as pool:
            for found,report in pool.map(lambda d:self._directory(d,identity),self.config['directories']):
                sources.extend(found);diagnostics.append(report)
        sources=list({s['url']:s for s in sources}.values())[:8]
        if identity['id'].startswith('record:query:') and sources:
            first=sources[0]
            identity=dict(id='record:official:'+first['provider']+':'+urlsplit(first['url']).path.strip('/').replace('/','-'),name=first['artist']['name'],aliases=list(dict.fromkeys([query,*[n for s in sources for n in s['artist'].get('aliases',[])]])))
        for source in sources:
            source['artist']=identity
        albums={}
        with ThreadPoolExecutor(max_workers=4) as pool:
            for entries,report in pool.map(self._albums,sources):
                diagnostics.extend(report.pop('detailSources',[]))
                diagnostics.append(report)
                for album in entries:
                    albums.setdefault(rules.norm(album['title']),album)
        failed=[d for d in diagnostics if d['status'] not in {'ok','unconfirmed','not_found'}]
        if albums:
            status='partial' if failed else 'confirmed'
        elif failed:
            status='blocked' if all(d['status']=='blocked' for d in failed) else 'fetch_error'
        else:
            status='unconfirmed' if sources else 'not_found'
        return dict(version=1,status=status,artist=dict(identity,albums=list(albums.values())),sources=diagnostics,cache={'hit':False,'refreshFailed':False},coverage='取得できた公式資料の範囲。全作品や公式サイトの不存在を断定しません。')
