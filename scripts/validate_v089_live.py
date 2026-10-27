"""Read-only live prototype validation; loopback API only, no public deployment."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time
from urllib.parse import urlencode,urlsplit
from urllib.request import Request,urlopen
from wsgiref.simple_server import make_server
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from server.prototype import prototype_app
from server.app import ThreadedServer
from scripts.configure_public_api import configure

ORIGIN='https://dqsh55-design.github.io'
API='https://record-v089-api.test'

def validate(browser=False):
    from server.source_policy import SourcePolicy
    policy=SourcePolicy.load()
    if not any(policy.permits(host) for host in policy.document['hosts']):
        from scripts.validate_v090_readiness import validate as readiness
        return readiness() # No old live probe when source permission is unclear.
    app=prototype_app();server=make_server('127.0.0.1',0,app,server_class=ThreadedServer)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(server.server_port)
    report={'version':'v0.89','checkedAt':datetime.now(timezone.utc).isoformat(),'publicDeployment':False,'registeredArtistsAdded':0,'catalogSha256':hashlib.sha256((ROOT/'data/official-catalog.json').read_bytes()).hexdigest(),'mode':'Pages UI + loopback Python official fetch prototype','searches':[]}
    def request(path,origin=ORIGIN):
        with urlopen(Request(base+path,headers={'Origin':origin}),timeout=150) as response:return response.status,dict(response.headers),response.read()
    try:
        for name in ['Willie Nelson','Jimi Hendrix','Miles Davis','Willie Nelson']:
            started=time.monotonic();status,headers,raw=request('/api/search?'+urlencode({'q':name}));body=json.loads(raw)
            assert status==200 and headers.get('Access-Control-Allow-Origin')==ORIGIN
            assert all(a['year'] and a['label'] and a['sourceUrl'].startswith('https:') and a['generationProof'] for a in body['artist']['albums'])
            report['searches'].append({'query':name,'elapsedSeconds':round(time.monotonic()-started,3),'result':body})
        assert report['searches'][3]['result']['cache']['hit']
        if browser:
            from playwright.sync_api import sync_playwright,expect
            with sync_playwright() as p:
                executable=os.environ.get('RECORD_CHROMIUM') or shutil.which('google-chrome') or shutil.which('chromium')
                chromium=p.chromium.launch(**({'executable_path':executable} if executable else {}));context=chromium.new_context(viewport={'width':390,'height':844});page=context.new_page();errors=[];unexpected=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                def route(r):
                    url=urlsplit(r.request.url)
                    if r.request.url==ORIGIN+'/record/':r.fulfill(body=configure((ROOT/'index.html').read_text(),API,mode='hybrid'),content_type='text/html');return
                    if r.request.url==ORIGIN+'/record/data/official-catalog.json':r.fulfill(body=(ROOT/'data/official-catalog.json').read_text(),content_type='application/json');return
                    if url.netloc==urlsplit(API).netloc and url.path=='/api/search':
                        status,headers,raw=request(url.path+'?'+url.query,r.request.headers.get('origin',''));r.fulfill(status=status,headers=headers,body=raw);return
                    unexpected.append(r.request.url);r.abort()
                page.route('**/*',route);page.goto(ORIGIN+'/record/')
                browser_results=[]
                for query in ['Willie Nelson','Jimi Hendrix','Miles Davis']:
                    page.get_by_role('textbox',name='アーティスト名').fill(query);page.get_by_role('button',name='検索',exact=True).click()
                    expect(page.get_by_role('button',name='検索',exact=True)).to_be_enabled(timeout=150000)
                    expect(page.locator('#status')).not_to_be_empty()
                    if query=='Willie Nelson':expect(page.locator('article').first).to_be_visible()
                    if query=='Jimi Hendrix':expect(page.locator('#status')).to_have_attribute('data-state','policy_restricted');expect(page.locator('article')).to_have_count(0)
                    if query=='Miles Davis':expect(page.locator('article')).to_have_count(72)
                    browser_results.append({'query':query,'state':page.locator('#status').get_attribute('data-state'),'visibleWorks':page.locator('article').count(),'totalText':page.locator('#catalog-total').inner_text(),'horizontalOverflow':page.evaluate('document.documentElement.scrollWidth>innerWidth')})
                assert not errors and not unexpected
                report['browser']={'origin':ORIGIN,'apiMapping':'Test HTTPS API origin mapped to a real loopback HTTP API; no cloud deployment or publisher-CORS override','results':browser_results,'pageErrors':errors,'unexpectedRequests':unexpected,'browserVersion':chromium.version}
                context.close();chromium.close()
    finally:server.shutdown();server.server_close();thread.join(timeout=2);app.service.cache.close()
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--browser',action='store_true');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=validate(args.browser);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
