"""New public source-first UI contract; real reviewed data, mocked networking."""
import copy
import json
import os
from pathlib import Path
import shutil
import unittest
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect
ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / 'data/official-catalog.json').read_text())

class OfficialCatalogUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = sync_playwright().start()
        executable = os.environ.get('RECORD_CHROMIUM') or shutil.which('chromium') or shutil.which('google-chrome')
        cls.browser = cls.p.chromium.launch(**({'executable_path': executable} if executable else {}))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.p.stop()

    def page(self, width=390, catalog=None, failure=False):
        context = self.browser.new_context(viewport={'width': width, 'height': 844})
        self.addCleanup(context.close)
        page = context.new_page()
        errors, remote = [], []
        page.on('pageerror', lambda e: errors.append(str(e)))
        self.addCleanup(lambda: self.assertEqual(errors, []))
        def route(r):
            u = urlparse(r.request.url)
            if u.hostname == 'record.test' and u.path == '/record/':
                r.fulfill(body=(ROOT / 'index.html').read_text(), content_type='text/html')
            elif u.hostname == 'record.test' and u.path == '/record/data/official-catalog.json':
                r.fulfill(status=503 if failure else 200, json=CATALOG if catalog is None else catalog)
            else:
                remote.append(r.request.url)
                if u.hostname == 'musicbrainz.org' and u.path.endswith('/artist'):
                    r.fulfill(json={'artists': [{'id':'unknown','name':'Unknown Artist'}]})
                else:
                    r.abort()
        page.route('**/*', route)
        page.goto('http://record.test/record/')
        return page, remote

    def search(self, page, name):
        page.get_by_role('textbox', name='アーティスト名').fill(name)
        page.get_by_role('button', name='検索', exact=True).click()

    def test_norah_then_miles_without_musicbrainz(self):
        for width in (320, 390, 430):
            with self.subTest(width=width):
                page, remote = self.page(width)
                self.search(page, 'ノラ・ジョーンズ')
                expect(page.locator('#official-catalog article')).to_have_count(12)
                expect(page.get_by_text('Not Too Late', exact=True)).to_be_visible()
                expect(page.locator('#official-catalog .meta').filter(has_text='2007')).to_have_count(1)
                self.assertEqual(remote, [])
                self.search(page, 'マイルス・デイビス')
                expect(page.locator('#official-catalog article')).to_have_count(8)
                expect(page.get_by_text('The Essential Miles Davis', exact=True)).to_be_visible()
                expect(page.get_by_text('Doo-Bop', exact=True)).to_be_visible()
                expect(page.get_by_text('TUTU', exact=True)).to_be_visible()
                expect(page.get_by_text('Norah Jones の正規発売確認済みアルバム')).to_have_count(0)
                self.assertEqual(remote, [])
                self.assertFalse(page.evaluate('document.documentElement.scrollWidth > innerWidth'))
                for link in page.locator('#official-catalog a').all():
                    self.assertEqual(link.get_attribute('target'), '_blank')
                    self.assertIn('noopener', link.get_attribute('rel'))
                self.assertEqual(page.locator('#official-catalog a').filter(has_text='発売の根拠').count(),8)
                self.assertEqual(page.locator('#official-catalog a').filter(has_text='配信先は未確認').count(),8)

    def test_unconfirmed_injected_album_is_hidden(self):
        catalog=copy.deepcopy(CATALOG)
        bad=copy.deepcopy(catalog['artists'][0]['albums'][0])
        bad.update(id='fake', title='Unverified Bootleg', official=False)
        catalog['artists'][0]['albums'].append(bad)
        page,_=self.page(catalog=catalog)
        self.search(page,'Norah Jones')
        expect(page.locator('#official-catalog article')).to_have_count(12)
        expect(page.get_by_text('Unverified Bootleg')).to_have_count(0)

    def test_catalog_failure_has_no_database_fallback(self):
        page,remote=self.page(failure=True)
        self.search(page,'Norah Jones')
        expect(page.locator('#status')).to_contain_text('公式目次を読み込めませんでした')
        expect(page.locator('article')).to_have_count(0)
        self.assertEqual(remote,[])

    def test_unknown_artist_cannot_promote_database_results(self):
        page,_=self.page()
        self.search(page,'Unknown Artist')
        page.get_by_role('button',name='この名義の作品を見る →').click()
        expect(page.locator('#official-catalog')).to_contain_text('公式発売資料はまだ登録されていません')
        expect(page.locator('#official-catalog article')).to_have_count(0)

    def test_saved_records_preserved_and_export_available(self):
        page,_=self.page()
        page.evaluate("localStorage.setItem('recordVerifiedLinks', JSON.stringify({'saved':'value'}))")
        self.search(page,'Norah Jones')
        self.assertEqual(page.evaluate("JSON.parse(localStorage.getItem('recordVerifiedLinks')).saved"),'value')
        expect(page.get_by_text('保存記録のバックアップ・復元')).to_be_visible()

if __name__ == '__main__':
    unittest.main()
