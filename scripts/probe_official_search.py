"""Read-only v0.88 feasibility probe. Never writes or expands the public catalog."""
import argparse
from datetime import date, datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
import generate_official_catalog as rules
from official_discography import Links, safe_url

ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT))
from server.source_policy import SourcePolicy
ORIGIN='https://dqsh55-design.github.io'
ARTIST={'name':'Willie Nelson','aliases':['ウィリー・ネルソン','ウィリーネルソン']}
SOURCES=[
    {'id':'artist-discography','url':'https://willienelson.com/collections/music','host':'willienelson.com','adapter':'discovery'},
    {'id':'warner','url':'https://wmg.jp/WillieNelson/discography/album','host':'wmg.jp','adapter':'warner-albums-v1','label':'Warner Music Japan','releasePath':r'/WillieNelson/discography/\d+'},
    {'id':'bluenote','url':'https://www.bluenote.com/artist/willie-nelson/','host':'www.bluenote.com','adapter':'bluenote-artist-v1','label':'Blue Note Records','releasePath':r'/artist/willie-nelson/'}]


def approved_url(url):
    return url in {s['url'] for s in SOURCES} or (safe_url(url,'willienelson.com') and bool(re.fullmatch(r'/products/[a-z0-9-]+',urlsplit(url).path)) and not urlsplit(url).query and not urlsplit(url).fragment)


def cors_readable(allow_origin,origin=ORIGIN):
    # Requests omit credentials. No preflight, custom browser headers, or no-cors mode.
    return allow_origin in {'*',origin}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise ValueError('redirect_not_followed')


class ProbeTransport:
    def __init__(self,limit=7,timeout=12,access_policy=None):
        self.access_policy=access_policy or SourcePolicy.load()
        self.limit,self.timeout=limit,timeout
        self.cache={};self.blocked=set();self.last={};self.calls=0

    def __call__(self,url):
        if not approved_url(url):return {'url':url,'status':'unsafe_source'},''
        if url in self.cache:return self.cache[url]
        host=urlsplit(url).hostname
        if not self.access_policy.permits(host):return {'url':url,'status':'policy_restricted'},''
        if host in self.blocked:return {'url':url,'status':'blocked','code':'host_cooldown'},''
        if self.calls>=self.limit:return {'url':url,'status':'budget_exhausted'},''
        delay=self.last.get(host,0)+1-time.monotonic()
        if delay>0:time.sleep(min(delay,1))
        self.last[host]=time.monotonic();self.calls+=1
        info={'url':url,'observedAt':datetime.now(timezone.utc).isoformat(),'status':'fetch_error'};start=time.monotonic()
        try:
            request=Request(url,headers={'Origin':ORIGIN,'User-Agent':'RECORD-OfficialSourceProbe/0.88'})
            with build_opener(NoRedirect()).open(request,timeout=self.timeout) as response:
                info['httpStatus']=response.status
                info['allowOrigin']=response.headers.get('Access-Control-Allow-Origin','')
                info['corsHeaderAllowsPagesOrigin']=cors_readable(info['allowOrigin'])
                info['contentType']=response.headers.get('Content-Type','')
                if 'html' not in info['contentType'].lower():raise ValueError('unsupported_format')
                raw=response.read(2_000_001)
                if len(raw)>2_000_000:raise ValueError('response_too_large')
                body=raw.decode('utf-8')
                if re.search(r'<title[^>]*>\s*(Just a moment|Access Denied|Attention Required|Forbidden)',body,re.I):
                    self.blocked.add(host);raise ValueError('challenge_page')
                info.update(status='ok',sourceSha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
        except HTTPError as error:
            info.update(httpStatus=error.code,status='blocked' if error.code in {401,403,429} else 'not_found' if error.code==404 else 'fetch_error')
            if info['status']=='blocked':self.blocked.add(host)
            body=''
        except ValueError as error:
            info.update(status='blocked' if str(error)=='challenge_page' else 'fetch_error',code=str(error));body=''
        except (TimeoutError,URLError,UnicodeError):
            info['code']='network_or_encoding';body=''
        info['elapsedSeconds']=round(time.monotonic()-start,3)
        self.cache[url]=(info,body)
        return info,body


def discover_products(body):
    links=Links();links.feed(body);found={}
    for href,title in links.links:
        url=urljoin(SOURCES[0]['url'],href)
        if approved_url(url) and urlsplit(url).path.startswith('/products/') and title.strip():
            found.setdefault(url,{'title':title.strip(),'sourceUrl':url,'status':'candidate_only'})
    return list(found.values())


def inspect_product(candidate,body,today):
    """Product timestamps/vendor names are not an album release date or issuer."""
    source={'artist':ARTIST,'url':candidate['sourceUrl'],'host':'willienelson.com','releasePath':r'/products/[a-z0-9-]+'}
    accepted,held=rules.jsonld(source,body,today)
    # Only the existing strict MusicAlbum + MusicRelease rule may approve a product.
    # Shopify Product/Offer, stock status, vendor, article date and copyright are insufficient.
    return accepted,{'title':candidate['title'],'sourceUrl':candidate['sourceUrl'],'status':'confirmed' if accepted else 'unconfirmed','reason':'strict_music_release' if accepted else 'missing_explicit_music_release_artist_date_and_issuer'}


def probe(query,transport=None,today=None):
    today=today or date.today();transport=transport or ProbeTransport()
    result={'format':'RECORD-official-search-probe-v1','mode':'read-only-experiment','query':query,'checkedAt':today.isoformat(),'publicCatalogModified':False,'realtimePagesImplemented':False,'verifiedWorks':[],'heldCandidates':[],'sources':[],'discoveredProductCount':0,'coverage':'bounded_partial_probe_not_complete_discography'}
    if rules.norm(query) not in {rules.norm(n) for n in [ARTIST['name'],*ARTIST['aliases']]}:
        result['status']='unsupported_probe_artist';return result
    result['artist']=ARTIST['name'];seen=set();candidates=[]
    def accept(items,info,source):
        for item in items:
            key=rules.norm(item['title'])
            if key in seen:continue
            seen.add(key)
            result['verifiedWorks'].append({'title':item['title'],'artist':ARTIST['name'],'year':item.get('listedReleaseDate',item.get('listedReleaseYear',''))[:4],'label':item.get('label',source.get('label')),'sourceUrl':item['url'],'evidenceSourceUrl':source['url'],'sourceSha256':info['sourceSha256'],'listedReleaseDate':item.get('listedReleaseDate'),'listedReleaseYear':item.get('listedReleaseYear'),'checkedAt':today.isoformat(),'officialReleaseConfirmed':True,'rule':source['adapter'],'experimentalOnly':True})
    for source in SOURCES:
        info,body=transport(source['url']);info=dict(info,id=source['id']);result['sources'].append(info)
        if info['status']!='ok':continue
        if source['adapter']=='discovery':
            candidates=discover_products(body);result['discoveredProductCount']=len(candidates);continue
        try:
            accepted,held=rules.ADAPTERS[source['adapter']](dict(source,artist=ARTIST),body,today)
            accept(accepted,info,source);info.update(verifiedCount=len(accepted),heldCount=held)
        except (ValueError,KeyError,TypeError):info['parseStatus']='format_or_identity_mismatch'
    # Operational page budget, not an artist work-count limit. It is explicitly not complete.
    for candidate in candidates[:3]:
        info,body=transport(candidate['sourceUrl']);result['sources'].append(dict(info,id='artist-product'))
        if info['status']!='ok':
            result['heldCandidates'].append(dict(candidate,status=info['status']));continue
        accepted,held=inspect_product(candidate,body,today);result['heldCandidates'].append(held)
        accept(accepted,info,dict(url=candidate['sourceUrl'],adapter='music-album-jsonld-v1'))
    result['status']='confirmed_partial' if result['verifiedWorks'] else 'retrieval_failed' if any(i['status']!='ok' for i in result['sources']) else 'no_confirmed_works'
    return result


def probe_directories(query,fetch=None,clock=None):
    """Exercise existing generic discovery with no artist anchors or disk database."""
    import sys
    sys.path.insert(0,str(ROOT))
    from server.search import OfficialSearch
    config=json.loads((ROOT/'data/official-realtime.json').read_text())
    config['identities']=[] # No Willie Nelson identity or album registrations.
    kwargs={} if clock is None else {'clock':clock}
    service=OfficialSearch(config,':memory:',fetch=fetch,**kwargs)
    try:
        raw=service.search(query)
    finally:service.cache.close()
    result={'format':'RECORD-official-search-probe-v1','mode':'directory-search-experiment','query':query,'checkedAt':datetime.fromtimestamp(service.clock(),timezone.utc).date().isoformat(),'status':raw['status'],'publicCatalogModified':False,'realtimePagesImplemented':False,'perArtistAnchorsConfigured':False,'verifiedWorks':[],'sources':raw['sources'],'coverage':raw['coverage']}
    for album in raw['artist']['albums']:
        proof=album['generationProof']
        # The preserved optional API returns year=None. Display only its verified release proof.
        year=(proof.get('listedReleaseDate') or proof.get('listedReleaseYear') or '')[:4]
        if not year:continue
        result['verifiedWorks'].append({'title':album['title'],'artist':raw['artist']['name'],'year':year,'label':album['label'],'sourceUrl':album['sourceUrl'],'sourceSha256':proof['sourceSha256'],'listedReleaseDate':proof.get('listedReleaseDate'),'listedReleaseYear':proof.get('listedReleaseYear'),'checkedAt':album['checkedAt'],'officialReleaseConfirmed':True,'rule':proof['rule'],'experimentalOnly':True})
    return result


def render_report(result):
    rows=[]
    for work in result['verifiedWorks']:
        if work.get('officialReleaseConfirmed') is not True:continue
        rows.append('<tr>'+''.join('<td>'+escape(str(work[k]))+'</td>' for k in ['title','artist','year','label'])+'<td><a rel="noopener noreferrer" href="'+escape(work['sourceUrl'],quote=True)+'">公式発売の根拠</a></td></tr>')
    return '<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RECORD 公式取得の検証結果</title><style>body{font:16px/1.8 system-ui;max-width:960px;margin:32px auto;padding:0 16px}table{border-collapse:collapse;width:100%}td,th{padding:12px;text-align:left;border-bottom:1px solid #ddd;overflow-wrap:anywhere}.table{overflow:auto}</style><h1>公式取得の検証結果</h1><p>実行時に取得した資料のスナップショット。公開目次には未登録です。このHTMLを開いた時に再調査はしません。</p><p>確認日：'+escape(result['checkedAt'])+' ／状態：'+escape(result['status'])+'</p><div class="table"><table><thead><tr><th>作品名</th><th>アーティスト</th><th>発売年</th><th>発売元</th><th>根拠</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div><p>未確認の候補は上の発売確認済み一覧に表示しません。ブラウザのCORS検証結果は別ファイルです。</p></html>'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--artist',default='Willie Nelson');parser.add_argument('--directory-search',action='store_true');parser.add_argument('--output-dir',required=True);args=parser.parse_args()
    out=Path(args.output_dir).resolve()
    if out==ROOT or out==ROOT/'data' or ROOT/'data' in out.parents:parser.error('public catalog directories are not probe outputs')
    result=probe_directories(args.artist) if args.directory_search else probe(args.artist);out.mkdir(parents=True,exist_ok=True)
    (out/'official-search-probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (out/'official-search-probe.html').write_text(render_report(result))
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
