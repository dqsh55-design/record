"""The default Pages UI runs against real shipped files; all other HTTP is denied."""
import copy
import json
import os
import re
from pathlib import Path
import shutil
import unittest
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
CATALOG=json.loads((ROOT/'data/official-catalog.json').read_text())

class PagesUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=sync_playwright().start()
        executable=os.environ.get('RECORD_CHROMIUM') or shutil.which('chromium') or shutil.which('google-chrome')
        cls.browser=cls.p.chromium.launch(**({'executable_path':executable} if executable else {}))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.p.stop()

    def page(self,width=390,catalog=None,fail_once=False):
        context=self.browser.new_context(viewport={'width':width,'height':844})
        self.addCleanup(context.close)
        page=context.new_page();requests=[];unexpected=[];errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        self.addCleanup(lambda:self.assertEqual(errors,[]))
        def route(r):
            url=urlparse(r.request.url)
            if url.hostname=='record.test' and url.path=='/record/':
                r.fulfill(body=(ROOT/'index.html').read_text(),content_type='text/html');return
            if url.hostname=='record.test' and url.path=='/record/data/official-catalog.json':
                requests.append(r.request.url)
                if fail_once and len(requests)==1:r.fulfill(status=503,body='Unavailable');return
                r.fulfill(json=CATALOG if catalog is None else catalog);return
            unexpected.append(r.request.url);r.abort()
        page.route('**/*',route);page.goto('http://record.test/record/')
        self.addCleanup(lambda:self.assertEqual(unexpected,[]))
        return page,requests

    def search(self,page,name):
        page.get_by_role('textbox',name='アーティスト名').fill(name)
        page.get_by_role('button',name='検索',exact=True).click()

    def test_three_mobile_widths_real_catalog_and_source_links(self):
        for width in [320,390,430]:
            with self.subTest(width=width):
                page,requests=self.page(width)
                expect(page.locator('#catalog-total')).to_have_text('公式発売確認済み · 登録199作品')
                expect(page.locator('#catalog-artists')).to_have_count(0)
                self.search(page,'ノラ・ジョーンズ')
                expect(page.locator('#official-catalog article')).to_have_count(13)
                expect(page.locator('#official-catalog .sub')).to_contain_text('リアルタイム検索ではなく')
                for link in page.locator('#official-catalog article a').all():
                    href=link.get_attribute('href')
                    self.assertTrue(href.startswith(('https://www.bluenote.com/','https://www.universal-music.co.jp/','https://music.youtube.com/search?q=','https://music.youtube.com/playlist?list=OLAK5uy_')))
                    self.assertEqual(link.get_attribute('rel'),'noopener noreferrer')
                self.search(page,'マイルス・デイビス')
                expect(page.locator('#official-catalog article')).to_have_count(72)
                expect(page.get_by_text('Kind Of Blue',exact=True)).to_be_visible()
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width)
                self.assertEqual(len(requests),1)

    def test_confirmed_album_opens_directly_and_keeps_official_source_and_search(self):
        page,_=self.page();self.search(page,'Norah Jones')
        expected=next(a for a in CATALOG['artists'][0]['albums'] if a['title']=='Visions')
        card=page.locator('article').filter(has=page.get_by_text('Visions',exact=True))
        link=card.get_by_role('link',name='YouTube Musicでアルバムを開く ↗',exact=True)
        expect(link).to_have_attribute('href',expected['listeningLink']['url'])
        card.locator('summary').click()
        expect(card.get_by_role('link',name='発売の根拠：Blue Note Records ↗',exact=True)).to_have_attribute('href',expected['sourceUrl'])
        expect(card.get_by_role('link',name='別の配信をYouTube Musicで探す ↗',exact=True)).to_have_attribute('href',re.compile(r'^https://music\.youtube\.com/search\?q='))
        destinations=[]
        def destination(route):
            destinations.append(route.request.url)
            route.fulfill(body='<title>Verified link destination test</title>',content_type='text/html')
        page.context.route('https://music.youtube.com/**',destination)
        with page.expect_popup() as popup:link.click()
        popup.value.wait_for_load_state()
        self.assertEqual(destinations,[expected['listeningLink']['url']])

    def test_norah_and_miles_unconfirmed_listening_targets_stay_search_links(self):
        page,_=self.page()
        for name,title in [('Norah Jones','Come Away With Me'),('Miles Davis','Kind Of Blue')]:
            self.search(page,name)
            card=page.locator('article').filter(has=page.get_by_text(title,exact=True))
            expect(card.get_by_role('link',name='YouTube Musicで探す（配信先は未確認） ↗',exact=True)).to_have_attribute('href',re.compile(r'^https://music\.youtube\.com/search\?q='))
            expect(card.get_by_role('link',name='YouTube Musicでアルバムを開く ↗',exact=True)).to_have_count(0)

    def test_new_official_works_are_visible_with_evidence_and_search_fallback(self):
        page,_=self.page()
        for artist,title,source in [
            ('Norah Jones','Covers（カヴァーズ〜私のお気に入り）','https://www.universal-music.co.jp/norah-jones/products/tocp-71410/'),
            ('Miles Davis','Live-Evil','https://www.milesdavis.com/albums/live-evil/'),
            ('Miles Davis','You’re Under Arrest','https://www.milesdavis.com/albums/youre-under-arrest/')]:
            self.search(page,artist)
            card=page.locator('article').filter(has=page.get_by_text(title,exact=True))
            expect(card).to_have_count(1)
            card.locator('summary').click()
            expect(card.get_by_role('link',name=re.compile('発売の根拠'))).to_have_attribute('href',source)
            expect(card.get_by_role('link',name='YouTube Musicで探す（配信先は未確認） ↗',exact=True)).to_be_visible()
            expect(card.locator('img')).to_have_count(0)

    def test_miles_twelve_new_listings_and_verified_birth_link(self):
        page,_=self.page();self.search(page,'マイルス・デイヴィス')
        expect(page.locator('#official-catalog article')).to_have_count(72)
        additions=[a for a in CATALOG['artists'][1]['albums'] if a['id'].startswith('official:miles-discography-20261027:')]
        self.assertEqual(len(additions),12)
        for album in additions:
            card=page.locator('article').filter(has=page.get_by_text(album['title'],exact=True))
            expect(card).to_have_count(1)
            card.locator('summary').click()
            expect(card.get_by_role('link',name='発売の根拠：Miles Davis Official Site ↗',exact=True)).to_have_attribute('href',album['sourceUrl'])
            if album.get('listeningLink'):
                expect(card.get_by_role('link',name='YouTube Musicでアルバムを開く ↗',exact=True)).to_have_attribute('href',album['listeningLink']['url'])
            else:
                expect(card.get_by_role('link',name='YouTube Musicで探す（配信先は未確認） ↗',exact=True)).to_have_attribute('href',re.compile(r'^https://music\.youtube\.com/search\?q='))
            expect(card.locator('img')).to_have_count(0)

    def test_bill_additions_and_canonical_direct_link(self):
        page,_=self.page();self.search(page,'ビル・フリゼール')
        expect(page.locator('#official-catalog article')).to_have_count(9)
        bill=next(a for a in CATALOG['artists'] if a['name']=='Bill Frisell')
        added=[a for a in bill['albums'] if a['id'].startswith('official:hundred-20261027:')]
        self.assertEqual(len(added),5)
        for album in added:
            card=page.locator('article').filter(has=page.get_by_text(album['title'],exact=True))
            expect(card).to_have_count(1)
            card.locator('summary').click()
            expect(card.get_by_role('link',name=re.compile('発売の根拠'))).to_have_attribute('href',album['sourceUrl'])
            if album.get('listeningLink'):
                expect(card.get_by_role('link',name='YouTube Musicでアルバムを開く ↗',exact=True)).to_have_attribute('href',album['listeningLink']['url'])
            else:
                expect(card.get_by_role('link',name='YouTube Musicで探す（配信先は未確認） ↗',exact=True)).to_be_visible()
            expect(card.locator('img')).to_have_count(0)

    def test_new_miles_official_series_is_not_excluded_by_bootleg_word(self):
        page,_=self.page();self.search(page,'Miles Davis')
        expect(page.locator('#official-catalog article')).to_have_count(72)
        for title in ["Miles Davis Quintet - Live In Europe 1967: The Bootleg Series Vol. 1","Miles Davis, Volume 1","Miles Davis, Volume 2","Jazz Track"]:
            card=page.locator('article').filter(has=page.get_by_text(title,exact=True))
            expect(card).to_have_count(1)
            expect(card.get_by_role('link',name='YouTube Musicで探す（配信先は未確認） ↗',exact=True)).to_be_visible()

    def test_mobile_evidence_collapsed_keyboard_toggle_and_unchanged_links(self):
        for width in [320,390,430]:
            with self.subTest(width=width):
                page,_=self.page(width)
                for artist in CATALOG['artists']:
                    self.search(page,artist['name'])
                    cards=page.locator('#official-catalog article')
                    expect(cards).to_have_count(len(artist['albums']))
                    for album in artist['albums']:
                        card=cards.filter(has=page.get_by_role('heading',name=album['title'],exact=True))
                        expect(card.locator('.album-artist')).to_have_text(artist['name'])
                        expect(card.locator('.meta')).to_have_text((album.get('year') or '発売年未確認')+' · '+album['label'])
                        details=card.locator('details');expect(details).not_to_have_attribute('open','')
                        source=details.locator('a').first
                        expect(source).to_be_hidden();expect(source).to_have_attribute('href',album['sourceUrl'])
                        expect(details.get_by_text('資料確認日：'+album['checkedAt'],exact=True)).to_be_hidden()
                        primary=card.locator('.info > a')
                        from urllib.parse import quote
                        expected=album.get('listeningLink',{}).get('url') or 'https://music.youtube.com/search?q='+quote(artist['name']+' '+album['title'],safe="~()*!.'-")
                        expect(primary).to_have_attribute('href',expected)
                    first=cards.first;summary=first.locator('summary')
                    summary.focus();summary.press('Enter')
                    expect(first.locator('details')).to_have_attribute('open','')
                    expect(first.locator('details a').first).to_be_visible()
                    expect(first.get_by_text('資料確認日：'+artist['albums'][0]['checkedAt'],exact=True)).to_be_visible()
                    self.assertGreaterEqual(summary.bounding_box()['height'],44)
                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width)
                    summary.press('Space');expect(first.locator('details a').first).to_be_hidden()

    def test_artist_japanese_aliases_evidence_and_reviewed_links(self):
        page,requests=self.page()
        for name in ['The Beatles','Led Zeppelin','Black Sabbath','Metallica','Kraftwerk','Daft Punk','David Bowie','Michael Jackson','Ryuichi Sakamoto']:
            artist=next(a for a in CATALOG['artists'] if a['name']==name)
            self.search(page,artist['aliases'][0])
            cards=page.locator('#official-catalog article');expect(cards).to_have_count(len(artist['albums']))
            expect(page.locator('#official-catalog h2')).to_contain_text(name)
            for album in artist['albums']:
                card=cards.filter(has=page.get_by_role('heading',name=album['title'],exact=True))
                expect(card.locator('details a').first).to_be_hidden()
                card.locator('summary').click()
                expect(card.get_by_role('link',name=re.compile('発売の根拠'))).to_have_attribute('href',album['sourceUrl'])
                if album.get('listeningLink'):
                    expect(card.get_by_role('link',name='YouTube Musicでアルバムを開く ↗',exact=True)).to_have_attribute('href',album['listeningLink']['url'])
                else:
                    expect(card.get_by_role('link',name='YouTube Musicで探す（配信先は未確認） ↗',exact=True)).to_be_visible()
        self.assertEqual(len(requests),1)
        self.search(page,"B’z")
        expect(page.locator('#status')).to_have_attribute('data-state','catalog_unsupported')
        expect(page.locator('#official-catalog article')).to_have_count(0)

    def test_deeper_live_compilation_and_reissue_catalogs(self):
        page,_=self.page()
        for name,title in [('The Beatles','Live At The BBC'),('Led Zeppelin','Mothership'),('Black Sabbath','ベスト・オブ・ディオ・イヤーズ'),('Metallica','S&M2'),('Kraftwerk','3-D 12345678'),('David Bowie','Stage 2017（ステージ 2017ミックス）'),('Michael Jackson','XSCAPE'),('Ryuichi Sakamoto','out of noise')]:
            self.search(page,name)
            artist=next(a for a in CATALOG['artists'] if a['name']==name)
            expect(page.locator('#official-catalog article')).to_have_count(len(artist['albums']))
            card=page.locator('article').filter(has=page.get_by_role('heading',name=title,exact=True))
            expect(card).to_have_count(1)
            expect(card.locator('details a').first).to_be_hidden()
            expect(card.get_by_role('link',name='YouTube Musicで探す（配信先は未確認） ↗',exact=True)).to_be_visible()
            card.locator('summary').click()
            expect(card.locator('details a').first).to_be_visible()
        self.search(page,'ダフト・パンク')
        for title in ['Human After All','Alive 2007']:
            album=next(a for a in CATALOG['artists'][10]['albums'] if a['title']==title)
            card=page.locator('article').filter(has=page.get_by_role('heading',name=title,exact=True))
            expect(card.get_by_role('link',name='YouTube Musicでアルバムを開く ↗',exact=True)).to_have_attribute('href',album['listeningLink']['url'])
        card=page.locator('article').filter(has=page.get_by_role('heading',name='Alive 1997',exact=True))
        expect(card.locator('.meta')).to_contain_text('2001')
        expect(card.get_by_role('link',name='YouTube Musicで探す（配信先は未確認） ↗',exact=True)).to_be_visible()

    def test_all_artists_remain_searchable_with_artist_count_and_persistent_total(self):
        page,requests=self.page()
        for artist in CATALOG['artists']:
            self.search(page,artist['name'])
            expect(page.locator('#official-catalog article')).to_have_count(len(artist['albums']))
            expect(page.locator('#status')).to_have_text(artist['name']+'：登録'+str(len(artist['albums']))+'作品（公式発売確認済み）')
            expect(page.locator('#catalog-total')).to_have_text('公式発売確認済み · 登録199作品')
            expect(page.locator('#catalog-artists')).to_have_count(0)
        self.assertEqual(len(requests),1)

    def test_home_stays_compact_when_more_artists_are_registered(self):
        many=copy.deepcopy(CATALOG)
        for i in range(200):
            many['artists'].append({'id':'test:artist:'+str(i),'name':'Additional Artist '+str(i),'aliases':[],
                'albums':[dict(CATALOG['artists'][0]['albums'][0],id='test:album:'+str(i))]})
        for width in [320,390,430]:
            with self.subTest(width=width):
                page,_=self.page(width,catalog=many)
                expect(page.locator('#catalog-total')).to_have_text('公式発売確認済み · 登録399作品')
                expect(page.locator('#catalog-artists')).to_have_count(0)
                expect(page.locator('#results')).to_be_empty()
                field=page.get_by_role('textbox',name='アーティスト名')
                expect(field).to_be_in_viewport()
                self.assertGreaterEqual(field.bounding_box()['height'],44)
                self.assertGreaterEqual(page.locator('#submit').bounding_box()['height'],44)
                self.assertLess(page.locator('#catalog-total').bounding_box()['y'],600)
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),width)
                for selector in ['.intro','.hint','#catalog-total']:
                    self.assertGreaterEqual(page.locator(selector).evaluate('el=>parseFloat(getComputedStyle(el).fontSize)'),14)

    def test_unknown_names_clear_old_cards_and_do_not_claim_no_official_site(self):
        page,_=self.page();self.search(page,'Norah Jones')
        expect(page.locator('#official-catalog article')).to_have_count(13)
        self.search(page,'Jimi Hendrix')
        expect(page.locator('#status')).to_have_attribute('data-state','catalog_unsupported')
        expect(page.locator('#status')).to_contain_text('未対応の可能性')
        expect(page.locator('#official-catalog')).to_have_count(0)
        # No network fallback, even for names that the optional API can handle.
        expect(page.locator('#status')).to_contain_text('存在しないという意味ではありません')

    def test_catalog_http_failure_has_retry_separate_from_unsupported(self):
        page,requests=self.page(fail_once=True)
        expect(page.locator('#status')).to_have_attribute('data-state','catalog_error')
        expect(page.locator('#catalog-total')).to_have_text('登録作品数を読み込めませんでした。')
        expect(page.locator('#status')).to_contain_text('通信環境')
        page.get_by_role('button',name='目次を再読み込み').click()
        expect(page.locator('#status')).to_have_attribute('data-state','catalog_ready')
        expect(page.locator('#catalog-total')).to_have_text('公式発売確認済み · 登録199作品')
        self.search(page,'Norah Jones')
        expect(page.locator('#official-catalog article')).to_have_count(13)
        self.assertEqual(len(requests),2)

    def test_malformed_catalog_is_fetch_problem_not_empty_discography(self):
        page,_=self.page(catalog={'version':1,'artists':[None]})
        expect(page.locator('#status')).to_have_attribute('data-state','catalog_error')
        expect(page.locator('#official-catalog')).to_have_count(0)

    def test_unverified_future_and_unsafe_rows_never_render(self):
        catalog=copy.deepcopy(CATALOG);artist=catalog['artists'][0]
        for index,patch in enumerate([{'official':False},{'sourceUrl':'https://evil.test/fake'},{'checkedAt':'2099-01-01'},{'reviewNote':''},{'verificationMethod':'official-source-rule-v1','generationProof':None}]):
            bad=dict(artist['albums'][0],id='fake:'+str(index),title='Unproven '+str(index));bad.update(patch);artist['albums'].append(bad)
        page,_=self.page(catalog=catalog);self.search(page,'Norah Jones')
        expect(page.locator('#official-catalog article')).to_have_count(13)
        expect(page.get_by_text('Unproven',exact=False)).to_have_count(0)

    def test_existing_browser_records_survive_static_search(self):
        page,_=self.page()
        page.evaluate("localStorage.setItem('recordVerifiedLinks',JSON.stringify({keep:'existing'}))")
        page.reload()
        expect(page.locator('#status')).to_have_attribute('data-state','catalog_ready')
        self.search(page,'Norah Jones')
        expect(page.locator('#official-catalog article')).to_have_count(13)
        self.assertEqual(page.evaluate("JSON.parse(localStorage.getItem('recordVerifiedLinks'))"),{'keep':'existing'})
        expect(page.get_by_text('保存記録のバックアップ・復元',exact=True)).to_be_visible()

    def test_rapid_search_uses_latest_input_and_reuses_shipped_catalog(self):
        page,requests=self.page()
        expect(page.locator('#status')).to_have_attribute('data-state','catalog_ready')
        page.evaluate("searchPublishedCatalog('Norah Jones');searchPublishedCatalog('Miles Davis')")
        expect(page.locator('#official-catalog h2')).to_contain_text('Miles Davis')
        expect(page.locator('#official-catalog article')).to_have_count(72)
        self.assertEqual(len(requests),1)


if __name__=='__main__':unittest.main()
