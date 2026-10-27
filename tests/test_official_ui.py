"""On-demand API UI contract; provider HTTP is synthetic, verification/cache are real."""
import copy
import json
import os
from pathlib import Path
import shutil
import unittest
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
from realtime_fixtures import make_service

ROOT=Path(__file__).resolve().parents[1]

class OnDemandUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=sync_playwright().start()
        executable=os.environ.get('RECORD_CHROMIUM') or shutil.which('chromium') or shutil.which('google-chrome')
        cls.browser=cls.p.chromium.launch(**({'executable_path':executable} if executable else {}))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.p.stop()

    def page(self,width=390,service_failure=False,status_override=None,inject=False,delay_first=False,api_origin=None,rate_limited=False):
        context=self.browser.new_context(viewport={'width':width,'height':844})
        self.addCleanup(context.close)
        service,pages=make_service();self.addCleanup(service.cache.close)
        page=context.new_page();errors=[];unexpected=[];pending=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        self.addCleanup(lambda:self.assertEqual(errors,[]))
        def route(r):
            url=urlparse(r.request.url)
            if url.hostname=='record.test' and url.path=='/record/':
                html=(ROOT/'index.html').read_text()
                if api_origin:html=html.replace('name="record-api-base" content=""','name="record-api-base" content="'+api_origin+'/"')
                r.fulfill(body=html,content_type='text/html');return
            if (url.hostname=='api.test' and url.path=='/api/search' if api_origin else url.hostname=='record.test' and url.path=='/record/api/search'):
                query=parse_qs(url.query)
                if rate_limited:
                    r.fulfill(status=429,json={'status':'rate_limited'});return
                if service_failure:
                    r.fulfill(status=503,json={'status':'service_unavailable'});return
                if delay_first and query['q'][0]=='Jimi Hendrix':
                    pending.append(r);return
                body=service.search(query['q'][0],refresh=query.get('refresh')==['1'])
                if status_override:
                    body['status']=status_override;body['artist']['albums']=[]
                    body['sources']=[dict(id='source',url='https://www.jimihendrix.com/music/',status='blocked' if status_override=='blocked' else 'fetch_error')]
                if inject and body['artist']['albums']:
                    bad=copy.deepcopy(body['artist']['albums'][0]);bad.update(id='generated:unproven',title='Unproven Listing',generationProof=None)
                    body['artist']['albums'].append(bad)
                    bad=copy.deepcopy(body['artist']['albums'][0]);bad.update(id='generated:expired',title='Expired Evidence',validUntilUnix=0)
                    body['artist']['albums'].append(bad)
                r.fulfill(json=body,headers={'Access-Control-Allow-Origin':'http://record.test'});return
            unexpected.append(r.request.url);r.abort()
        page.route('**/*',route);page.goto('http://record.test/record/')
        self.addCleanup(lambda:self.assertEqual(unexpected,[]))
        return page,service,pages,pending

    def search(self,page,name):
        page.get_by_role('textbox',name='アーティスト名').fill(name)
        page.get_by_role('button',name='検索',exact=True).click()

    def test_pages_uses_separate_https_api_origin(self):
        page,_,_,_=self.page(api_origin='https://api.test')
        self.search(page,'Norah Jones')
        expect(page.locator('#status')).to_contain_text('2作品')

    def test_rate_limit_explained_without_catalog_fallback(self):
        page,_,_,_=self.page(rate_limited=True)
        self.search(page,'Norah Jones')
        expect(page.locator('#status')).to_have_attribute('data-state','rate_limited')
        expect(page.locator('#status')).to_contain_text('1分')
        expect(page.locator('#official-catalog')).to_have_count(0)

    def test_three_artists_on_demand_at_mobile_widths(self):
        for width in (320,390,430):
            with self.subTest(width=width):
                page,_,_,_=self.page(width)
                for name,title,count in [('ジミ・ヘンドリックス','Are You Experienced',1),('ノラ・ジョーンズ','Come Away With Me',2),('マイルス・デイビス','Kind Of Blue',2)]:
                    self.search(page,name)
                    expect(page.locator('#official-catalog article')).to_have_count(count)
                    expect(page.get_by_text(title,exact=True)).to_be_visible()
                    self.assertFalse(page.evaluate('document.documentElement.scrollWidth>innerWidth'))
                    for link in page.locator('#official-catalog a').all():
                        self.assertEqual(link.get_attribute('target'),'_blank')
                        self.assertIn('noopener',link.get_attribute('rel'))
                page.locator('#search-sources summary').click()
                expect(page.locator('#search-sources')).to_contain_text('取得済み')

    def test_cache_reuse_and_explicit_refresh_failure(self):
        page,service,pages,_=self.page()
        self.search(page,'Norah Jones')
        expect(page.locator('#official-catalog article')).to_have_count(2)
        calls=len(pages.calls)
        self.search(page,'ノラジョーンズ')
        expect(page.locator('#status')).to_contain_text('再利用')
        self.assertEqual(len(pages.calls),calls)
        pages.fail=True
        page.get_by_role('button',name='公式情報を再確認').click()
        expect(page.locator('#status')).to_contain_text('再取得に失敗')
        expect(page.locator('#official-catalog article')).to_have_count(2)

    def test_unregistered_artist_discovered_at_search_time(self):
        page,_,_,_=self.page()
        self.search(page,'New Artist')
        expect(page.get_by_text('A Newly Discovered Album',exact=True)).to_be_visible()

    def test_unproven_and_expired_rows_hidden(self):
        page,_,_,_=self.page(inject=True)
        self.search(page,'Norah Jones')
        expect(page.locator('#official-catalog article')).to_have_count(2)
        expect(page.get_by_text('Unproven Listing')).to_have_count(0)
        expect(page.get_by_text('Expired Evidence')).to_have_count(0)

    def test_no_official_information_is_not_claimed_for_access_failures(self):
        for state,text in [('blocked','アクセス制限'),('fetch_error','取得に失敗'),('not_found','検索した公式情報源では'),('unconfirmed','正式発売済みと確認できるアルバムはありません')]:
            with self.subTest(state=state):
                page,_,_,_=self.page(status_override=state)
                self.search(page,'Jimi Hendrix')
                expect(page.locator('#status')).to_contain_text(text)
                expect(page.locator('article')).to_have_count(0)
                self.assertEqual(page.locator('#status').get_attribute('data-state'),state)

    def test_api_unavailable_has_no_prebuilt_or_database_fallback(self):
        page,_,_,_=self.page(service_failure=True)
        self.search(page,'Norah Jones')
        expect(page.locator('#status')).to_contain_text('公式検索サービスに接続できませんでした')
        expect(page.locator('article')).to_have_count(0)
        self.assertEqual(page.locator('#status').get_attribute('data-state'),'service_unavailable')

    def test_saved_browser_records_unchanged(self):
        page,_,_,_=self.page()
        page.evaluate("localStorage.setItem('recordVerifiedLinks',JSON.stringify({'saved':'value'}))")
        self.search(page,'Norah Jones')
        expect(page.locator('#official-catalog article')).to_have_count(2)
        self.assertEqual(page.evaluate("JSON.parse(localStorage.getItem('recordVerifiedLinks')).saved"),'value')
        expect(page.get_by_text('保存記録のバックアップ・復元')).to_be_visible()

    def test_previous_search_cannot_overwrite_newer_result(self):
        page,_,_,pending=self.page(delay_first=True)
        self.search(page,'Jimi Hendrix')
        expect(page.locator('#status')).to_contain_text('確認しています')
        page.evaluate("document.getElementById('query').value='Norah Jones';document.getElementById('form').dispatchEvent(new Event('submit',{cancelable:true,bubbles:true}))")
        expect(page.get_by_text('Come Away With Me',exact=True)).to_be_visible()
        expect(page.get_by_text('Are You Experienced',exact=True)).to_have_count(0)
        for route in pending:
            try:route.abort()
            except Exception:pass

if __name__=='__main__':unittest.main()
