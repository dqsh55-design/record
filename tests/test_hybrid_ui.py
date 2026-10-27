"""Real UI + API/verification/cache, with explicitly synthetic official HTTP."""
import copy
import json
import os
from pathlib import Path
import re
import shutil
import threading
import unittest
from urllib.parse import urlsplit,parse_qs
from wsgiref.simple_server import make_server
from playwright.sync_api import sync_playwright,expect
from realtime_fixtures import Pages,fixture_config,blue_page
from server.search import OfficialSearch,SourceError
from server.app import create_app,ThreadedServer
from server.prototype import prototype_app
from scripts.configure_public_api import configure
ROOT=Path(__file__).resolve().parents[1]

class HybridUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=sync_playwright().start();executable=os.environ.get('RECORD_CHROMIUM') or shutil.which('chromium') or shutil.which('google-chrome')
        cls.browser=cls.p.chromium.launch(**({'executable_path':executable} if executable else {}))
    @classmethod
    def tearDownClass(cls):cls.browser.close();cls.p.stop()

    def service(self,policy=False):
        pages=Pages();pages.pages['https://www.bluenote.com/artists/']+='<h5 class="post-name"><a href="/artist/willie-nelson/">Willie Nelson</a></h5>'
        pages.pages['https://www.bluenote.com/artist/willie-nelson/']=blue_page('Willie Nelson','willie-nelson',['American Classic'])
        def fetch(source):
            if policy and source['host']=='www.jimihendrix.com':raise SourceError('policy_restricted','terms_review_required')
            return pages(source)
        service=OfficialSearch(fixture_config(),':memory:',fetch=fetch);self.addCleanup(service.cache.close)
        return service,pages

    def page(self,width=390,policy=False,unavailable=False,inject=False,hold=False):
        service,pages=self.service(policy);app=create_app(service,allowed_origins=['https://record.test'])
        context=self.browser.new_context(viewport={'width':width,'height':844});self.addCleanup(context.close)
        page=context.new_page();errors=[];unexpected=[];requests=[];pending=[]
        page.on('pageerror',lambda e:errors.append(str(e)));self.addCleanup(lambda:self.assertEqual(errors,[]));self.addCleanup(lambda:self.assertEqual(unexpected,[]))
        def reply(route):
            if unavailable:route.fulfill(status=503,json={'status':'service_unavailable'},headers={'Access-Control-Allow-Origin':'https://record.test'});return
            url=urlsplit(route.request.url);environ={'REQUEST_METHOD':'GET','PATH_INFO':url.path,'QUERY_STRING':url.query,'HTTP_ORIGIN':route.request.headers.get('origin','')};response={}
            payload=b''.join(app(environ,lambda s,h:response.update(status=int(s.split()[0]),headers=dict(h))))
            if inject:
                body=json.loads(payload)
                if body.get('artist',{}).get('albums'):
                    bad=copy.deepcopy(body['artist']['albums'][0]);bad.update(id='generated:bad',title='Wrong Proof Year',year='2099');body['artist']['albums'].append(bad)
                    malformed=copy.deepcopy(bad);malformed['generationProof']['listedReleaseDate']=123;body['artist']['albums'].append(malformed)
                payload=json.dumps(body).encode();response['headers'].pop('Content-Length',None)
            route.fulfill(status=response['status'],headers=response['headers'],body=payload)
        def handle(route):
            url=urlsplit(route.request.url)
            if url.hostname=='record.test' and url.path=='/record/':route.fulfill(body=configure((ROOT/'index.html').read_text(),'https://api.test',mode='hybrid'),content_type='text/html');return
            if url.hostname=='record.test' and url.path=='/record/data/official-catalog.json':route.fulfill(body=(ROOT/'data/official-catalog.json').read_text(),content_type='application/json');return
            if url.hostname=='api.test' and url.path=='/api/search':
                requests.append(route.request)
                if hold:pending.append(route)
                else:reply(route)
                return
            unexpected.append(route.request.url);route.abort()
        page.route('**/*',handle);page.goto('https://record.test/record/')
        return page,service,pages,requests,pending,reply

    def search(self,page,name):
        page.get_by_role('textbox',name='アーティスト名').fill(name);page.get_by_role('button',name='検索',exact=True).click()

    def test_unknown_willie_live_fields_and_sources_at_three_mobile_widths(self):
        for width in [320,390,430]:
            with self.subTest(width=width):
                page,_,_,requests,_,_=self.page(width);self.search(page,'Willie Nelson')
                expect(page.locator('#official-catalog article')).to_have_count(1)
                expect(page.locator('.album-title')).to_have_text('American Classic')
                expect(page.locator('.album-artist')).to_have_text('Willie Nelson')
                expect(page.locator('.meta')).to_have_text('2002 · Blue Note Records') # Synthetic fixture year.
                expect(page.locator('#catalog-total')).to_have_text('公式発売確認済み · 登録292作品')
                card=page.locator('article');expect(card.locator('details a').first).to_be_hidden();card.locator('summary').click()
                expect(card.locator('details a').first).to_have_attribute('href','https://www.bluenote.com/artist/willie-nelson/')
                expect(card.get_by_role('link',name='YouTube Musicで探す（配信先は未確認） ↗',exact=True)).to_have_attribute('href',re.compile(r'^https://music.youtube.com/search\?q='))
                self.assertEqual(len(requests),1);self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width)
                expect(page.locator('#catalog-artists')).to_have_count(0);expect(page.locator('img')).to_have_count(0)

    def test_known_catalog_and_direct_links_survive_unknown_search(self):
        page,_,_,requests,_,_=self.page();self.search(page,'Willie Nelson');expect(page.locator('article')).to_have_count(1)
        self.search(page,'マイルス・デイビス');expect(page.locator('article')).to_have_count(72)
        self.search(page,'Norah Jones');expect(page.locator('article')).to_have_count(13)
        expect(page.get_by_role('link',name='YouTube Musicでアルバムを開く ↗',exact=True).first).to_be_visible()
        expect(page.get_by_text('保存記録のバックアップ・復元',exact=True)).to_be_visible();self.assertEqual(len(requests),1)

    def test_confirmed_cache_reused_without_more_official_requests(self):
        page,_,pages,_,_,_=self.page();self.search(page,'Willie Nelson');expect(page.locator('article')).to_have_count(1);before=len(pages.calls)
        self.search(page,'Miles Davis');expect(page.locator('article')).to_have_count(72)
        self.search(page,'Willie Nelson');expect(page.locator('#status')).to_contain_text('保存した確認済み情報を再利用')
        self.assertEqual(len(pages.calls),before)

    def test_api_failure_does_not_lose_registered_catalog(self):
        page,_,_,_,_,_=self.page(unavailable=True);self.search(page,'Willie Nelson');expect(page.locator('#status')).to_have_attribute('data-state','service_unavailable')
        expect(page.locator('article')).to_have_count(0);self.search(page,'Miles Davis');expect(page.locator('article')).to_have_count(72)

    def test_policy_stop_is_distinct_and_jimi_synthetic_proof_can_render(self):
        page,_,_,_,_,_=self.page(policy=True);self.search(page,'ジミ・ヘンドリックス')
        expect(page.locator('#status')).to_have_attribute('data-state','policy_restricted');expect(page.locator('#status')).to_contain_text('利用条件')
        expect(page.locator('article')).to_have_count(0)
        page,_,_,_,_,_=self.page();self.search(page,'Jimi Hendrix');expect(page.locator('article')).to_have_count(1)
        expect(page.locator('.meta')).to_contain_text('2001') # Parsing/renderer fixture, not live access approval.

    def test_wrong_year_cannot_render_as_official(self):
        page,_,_,_,_,_=self.page(inject=True);self.search(page,'Willie Nelson');expect(page.locator('article')).to_have_count(1)
        expect(page.get_by_text('Wrong Proof Year',exact=True)).to_have_count(0)

    def test_api_origin_credentials_rejected_and_browser_cookies_omitted(self):
        page,_,_,requests,_,_=self.page()
        page.context.add_cookies([{'name':'private','value':'never-send','domain':'api.test','path':'/','secure':True,'httpOnly':True}])
        self.search(page,'Willie Nelson');expect(page.locator('article')).to_have_count(1)
        self.assertNotIn('cookie',requests[0].headers)
        page.evaluate("document.querySelector('meta[name=record-api-base]').content='https://secret@api.test/'")
        self.search(page,'Jimi Hendrix');expect(page.locator('#status')).to_have_attribute('data-state','service_unavailable')
        self.assertEqual(len(requests),1)

    def test_late_api_response_cannot_replace_new_static_search(self):
        page,_,_,_,pending,reply=self.page(hold=True)
        with page.expect_request(re.compile(r'https://api\.test/api/search\?q=Willie')):
            page.evaluate('void searchRecord("Willie Nelson")')
        page.wait_for_function('document.getElementById("status").textContent.includes("公式ディスコグラフィー")')
        # Let routing receive the held request before switching the selected artist.
        page.wait_for_timeout(50);page.evaluate('searchRecord("Miles Davis")');expect(page.locator('article')).to_have_count(72)
        for route in pending:reply(route)
        page.wait_for_timeout(100);expect(page.locator('#official-catalog h2')).to_contain_text('Miles Davis')
        expect(page.locator('article')).to_have_count(72)

    def test_real_loopback_http_ui_api_roundtrip(self):
        service,_=self.service();server=make_server('127.0.0.1',0,prototype_app(service),server_class=ThreadedServer)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(lambda:(server.shutdown(),server.server_close(),thread.join(timeout=2)))
        context=self.browser.new_context();self.addCleanup(context.close);page=context.new_page();page.goto('http://127.0.0.1:'+str(server.server_port)+'/')
        self.search(page,'Willie Nelson');expect(page.locator('.album-title')).to_have_text('American Classic')
        self.search(page,'Miles Davis');expect(page.locator('article')).to_have_count(72)

if __name__=='__main__':unittest.main()
