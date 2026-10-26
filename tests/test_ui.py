"""Browser integration using generated evidence and intercepted external APIs.

No fixture is shipped as real catalog evidence. Run: python tests/test_ui.py
"""
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from verify_catalog import refresh_file

GROUP = '11111111-1111-1111-1111-111111111111'
ROOT = Path(__file__).resolve().parents[1]


def generated_catalog():
    detail = {'title': 'Album', 'artists': [{'name': 'Artist'}], 'label': 'Label',
              'publisher': 'Publisher', 'description': 'Long description: ' + 'x' * 500,
              'trackCount': 2, 'tracks': [{'title': 'One'}, {'title': 'Two'}]}
    release = {'id': GROUP, 'title': 'Album', 'status': 'Official',
               'artist-credit': [{'artist': {'name': 'Artist'}}],
               'label-info': [{'label': {'name': 'Label'}}], 'medium-count': 1,
               'media': [{'position': 1, 'track-count': 2, 'tracks': [
                   {'position': 1, 'title': 'One'}, {'position': 2, 'title': 'Two'}]}]}
    entries = [{'id': 'MPREb_' + state, 'title': state, 'year': '2001',
                'url': 'https://music.youtube.com/browse/MPREb_' + state,
                'artist_check': 'matched', 'mb_release_group': GROUP,
                'match_evidence': {'status': 'candidate', 'yt_label': 'Legacy Label', 'releases': []}}
               for state in ('supported', 'insufficient', 'different', 'stale', 'unverified')]

    def album(album_id):
        result = copy.deepcopy(detail)
        if album_id.endswith('insufficient'):
            result.pop('label')
        if album_id.endswith('different'):
            result['tracks'].reverse()
        return result

    mb = Mock()
    mb.get.side_effect = lambda path, **kw: {'releases': [{'id': GROUP}], 'count': 1} if path == 'release/' else release
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'ytmusic-albums.json'
        path.write_text(json.dumps({'Artist': entries}), encoding='utf-8')
        # Exercise the real producer -> JSON -> chooseArtist -> render route.
        catalog = refresh_file(path, Mock(get_album=album), mb, limit=4)
        catalog['Artist'][3]['automatic_verification']['checked_at'] = '2000-01-01T00:00:00Z'
        return catalog


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        executable = os.environ.get('RECORD_CHROMIUM') or shutil.which('chromium') or shutil.which('google-chrome')
        cls.browser = cls.playwright.chromium.launch(**({'executable_path': executable} if executable else {}))
        cls.catalog = generated_catalog()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def open_site(self, width=390, fail_mb=False, fail_catalog=False, fail_release=False, release_total=3, base_path=""):
        context = self.browser.new_context(viewport={'width': width, 'height': 844}, is_mobile=width < 500, has_touch=width < 500)
        self.addCleanup(context.close)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        self.addCleanup(lambda: self.assertEqual(errors, []))

        def route(request):
            url = urlparse(request.request.url)
            if url.hostname == 'record.test' and url.path == base_path + '/':
                request.fulfill(body=(ROOT / 'index.html').read_text(), content_type='text/html')
            elif url.path == base_path + '/data/ytmusic-albums.json':
                request.fulfill(status=503 if fail_catalog else 200, json={} if fail_catalog else self.catalog)
            elif url.hostname == 'musicbrainz.org':
                if fail_mb and url.path.endswith('/release-group'):
                    request.fulfill(status=403, json={'error': 'external service unavailable'})
                elif url.path.endswith('/artist'):
                    request.fulfill(json={'artists': [{'id': GROUP, 'name': 'Artist', 'type': 'Person'}]})
                elif url.path.endswith('/release'):
                    request.fulfill(status=503 if fail_release else 200, json={'release-count': release_total, 'releases': [
                        {'id': 'official', 'title': 'Official Album', 'status': 'Official', 'date': '1975', 'release-group': {'id': GROUP, 'primary-type': 'Album'}, 'label-info': [{'label': {'name': 'Epic'}, 'catalog-number': 'EPC 1'}]},
                        {'id': 'missing-label', 'title': 'Official without label', 'status': 'Official', 'release-group': {'primary-type': 'Album', 'secondary-types': ['Live']}},
                        {'id': 'bootleg', 'title': 'Bootleg hidden', 'status': 'Bootleg', 'release-group': {'primary-type': 'Album'}}]})
                elif url.path.endswith('/release/official'):
                    request.fulfill(json={'media': [{'position': 1, 'tracks': [{'position': 1, 'title': '<Song>'}]}]})
                elif url.path.endswith('/release-group'):
                    request.fulfill(json={'release-groups': [{'id': GROUP, 'title': 'supported', 'primary-type': 'Album', 'first-release-date': '2001'}], 'release-group-count': 1})
                else:
                    request.fulfill(json={'relations': []})
            else:
                request.fulfill(status=404, body='')

        page.route('**/*', route)
        page.goto('http://record.test' + base_path + '/')
        return page

    def search(self, page):
        page.get_by_role('textbox', name='アーティスト名').fill('Artist')
        page.get_by_role('button', name='検索', exact=True).click()
        page.get_by_role('button', name='この名義の作品を見る →').click()
        expect(page.locator('#status')).not_to_contain_text('アルバムを取得します', timeout=20000)
        expect(page.locator('#status')).not_to_contain_text('作品を読み込んでいます')
        page.get_by_text('以前のYouTube Music一覧・保存記録・照合ツール', exact=True).click()
        return page.locator('#results > details > section').first

    def test_v061_real_snapshots_and_distinct_modern_editions(self):
        # Captured MusicBrainz responses, replayed offline: not a live browser test.
        for name in ('Jeff-Beck', 'Miles-Davis'):
            page = self.open_site(375)
            data = json.loads((ROOT / 'docs/v0.61' / (name + '-releases.json')).read_text())
            page.route('**/ws/2/release?**', lambda route, request, data=data: route.fulfill(json=data))
            self.search(page)
            visible = [r for r in data['releases'] if r.get('status') not in ('Bootleg', 'Pseudo-Release', 'Promotion') and r.get('release-group', {}).get('primary-type') == 'Album']
            expect(page.locator('#official-releases article')).to_have_count(len({r['id'] for r in visible}))
            self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        page = self.open_site(390)
        records = [json.loads((ROOT / 'docs/v0.61' / (id + '.json')).read_text()) for id in (
            '6fbb6d1b-e6b4-4027-acf1-85045a0bd771', 'f5453a0d-414c-4974-b26f-9ceea9b35887')]
        page.route('**/ws/2/release?**', lambda route: route.fulfill(json={'release-count': 3, 'releases': records + [records[0]]}))
        self.search(page)
        section = page.locator('#official-releases')
        expect(section.locator('article')).to_have_count(2)
        expect(section).to_contain_text('8曲')
        expect(section).to_contain_text('9曲')
        for r in records:
            expect(section).to_contain_text(r['id'])
        output = os.environ.get('RECORD_SCREENSHOT_DIR')
        if output:
            Path(output).mkdir(parents=True, exist_ok=True)
            page.evaluate("document.getElementById('historical-catalog').open=false")
            page.screenshot(path=str(Path(output) / 'modern-jazz-trumpets-390.png'), full_page=True)

    def test_v061_automatic_link_requires_exact_release_evidence(self):
        page = self.open_site()
        page.route('**/ws/2/release?**', lambda route: route.fulfill(json={'release-count': 2, 'releases': [
            {'id': id, 'title': 'Album', 'status': 'Official', 'release-group': {'primary-type': 'Album'}} for id in (GROUP, 'different-edition')]}))
        self.search(page)
        section = page.locator('#official-releases')
        expect(section.get_by_role('link', name='根拠のあるアルバムを直接開く')).to_have_count(1)
        expect(section.get_by_role('link', name='YouTube Musicで探す ↗')).to_have_count(1)
        section.get_by_text('収録曲・曲順・リンクを確認', exact=True).first.click()
        expect(section).to_contain_text('一致した曲目：One / Two')
        page.evaluate("ytAlbums.forEach(a=>{if(a.automatic_verification)a.automatic_verification.checked_at='2000-01-01'});render()")
        expect(section.get_by_role('link', name='根拠のあるアルバムを直接開く')).to_have_count(0)

    def test_v061_cover_success_failure_and_mobile_layout(self):
        import base64
        page = self.open_site(320)
        pixel = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
        page.route('**/release/official/front-250', lambda route: route.fulfill(body=pixel, content_type='image/png'))
        page.route('**/release/missing-label/front-250', lambda route: route.fulfill(status=404))
        self.search(page)
        section = page.locator('#official-releases')
        image = section.locator('article').first.locator('img')
        expect(image).to_have_attribute('loading', 'lazy')
        expect(image).to_have_attribute('decoding', 'async')
        page.wait_for_function("document.querySelector('#official-releases img').naturalWidth > 0")
        section.locator('article').nth(1).scroll_into_view_if_needed()
        expect(section.locator('article').nth(1).locator('.cover')).to_have_text('画像なし')
        page.evaluate('render()')
        self.assertTrue(page.evaluate("coverFailures.has('missing-label')"))
        expect(section.locator('article')).to_have_count(2)
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))

    def test_v061_edition_link_save_reload_remove_and_backup(self):
        page = self.open_site(fail_catalog=True)
        page.route('**/ws/2/release?**', lambda route: route.fulfill(json={'release-count': 1, 'releases': [
            {'id': GROUP, 'title': 'Edition', 'status': 'Official', 'release-group': {'primary-type': 'Album'}}]}))
        self.search(page)
        section = page.locator('#official-releases')
        section.get_by_text('収録曲・曲順・リンクを確認', exact=True).click()
        field = section.get_by_role('textbox', name='Editionの発売盤リンク')
        field.fill('https://example.com/album')
        section.get_by_role('button', name='発売盤リンクを保存', exact=True).click()
        expect(section).to_contain_text('有効なYouTube MusicのアルバムURL')
        field.fill('https://music.youtube.com/browse/MPREb_edition?si=share')
        section.get_by_role('button', name='発売盤リンクを保存', exact=True).click()
        expect(section.get_by_role('link', name='保存したアルバムを開く（利用者登録）')).to_have_attribute('href', 'https://music.youtube.com/browse/MPREb_edition')
        expect(section).not_to_contain_text('正規盤確認済み')
        with page.expect_download() as pending:
            section.get_by_role('button', name='保存記録をバックアップ', exact=True).click()
        backup = json.loads(Path(pending.value.path()).read_text())
        self.assertEqual(backup['editionLinks'][GROUP]['source'], 'user')
        page.reload()
        self.search(page)
        expect(section.get_by_role('link', name='保存したアルバムを開く（利用者登録）')).to_be_visible()
        section.get_by_text('収録曲・曲順・リンクを確認', exact=True).click()
        section.get_by_role('button', name='発売盤リンクを削除', exact=True).click()
        expect(section.get_by_role('link', name='YouTube Musicで探す ↗')).to_be_visible()
        with page.expect_event('dialog') as dialog:
            section.get_by_label('保存記録を復元').set_input_files({'name': 'backup.json', 'mimeType': 'application/json', 'buffer': json.dumps(backup).encode()})
        dialog.value.accept()
        expect(section.get_by_role('link', name='保存したアルバムを開く（利用者登録）')).to_be_visible()

    def test_github_pages_repository_subpath(self):
        page = self.open_site(base_path='/record')
        section = self.search(page)
        expect(section.locator('article')).to_have_count(5)
        expect(page.locator('#official-releases article')).to_have_count(2)

    def test_release_catalog_works_without_youtube_catalog(self):
        page = self.open_site(fail_catalog=True, release_total=103)
        page.get_by_role('textbox', name='アーティスト名').fill('Artist')
        page.get_by_role('button', name='検索', exact=True).click()
        page.get_by_role('button', name='この名義の作品を見る →').click()
        section = page.locator('#official-releases')
        expect(section.locator('article')).to_have_count(2)
        section.get_by_role('button', name='さらに発売記録を読み込む', exact=True).click()
        expect(section).to_contain_text('6 / 103件取得')
        expect(section.locator('article')).to_have_count(2)
        expect(section.get_by_role('link', name='YouTube Musicで探す ↗')).to_have_count(2)

    def test_release_failure_shows_retry_and_legacy_data(self):
        page = self.open_site(fail_release=True)
        self.search(page)
        section = page.locator('#official-releases')
        expect(section).to_contain_text('発売記録を取得できませんでした')
        expect(section.get_by_role('button', name='発売記録の取得を再試行')).to_be_visible()

    def test_musicbrainz_first_official_editions(self):
        page = self.open_site()
        self.search(page)
        section = page.locator('#official-releases')
        expect(section.locator('article')).to_have_count(2)
        expect(section).to_contain_text('公式発売の登録あり')
        expect(section).to_contain_text('レーベル未登録')
        expect(section).not_to_contain_text('Bootleg hidden')
        expect(section.get_by_role('link', name='YouTube Musicで探す ↗').first).to_have_attribute('href', 'https://music.youtube.com/search?q=Artist%20Official%20Album')
        section.get_by_text('収録曲・曲順・リンクを確認', exact=True).first.click()
        section.get_by_role('button', name='曲目を取得', exact=True).first.click()
        expect(section).to_contain_text('1. <Song>')
        expect(section).to_contain_text('EPC 1')

    def test_same_title_editions_and_unknown_status_are_preserved(self):
        page = self.open_site()
        editions = [{'id': str(i), 'title': '同名アルバム', 'status': status,
                     'release-group': {'primary-type': 'Album', 'secondary-types': types}}
                    for i, (status, types) in enumerate([
                        ('Official', []), ('Official', ['Compilation']),
                        ('Official', ['Live']), ('Withdrawn', []), ('Bootleg', [])])]
        page.route('**/ws/2/release?**', lambda route: route.fulfill(json={'releases': editions, 'release-count': 5}))
        self.search(page)
        section = page.locator('#official-releases')
        expect(section.locator('article')).to_have_count(4)
        expect(section).to_contain_text('ベスト・編集盤')
        expect(section).to_contain_text('ライブ盤')
        expect(section).to_contain_text('発売区分：Withdrawn（確認待ち）')

    def test_primary_controls_with_touch(self):
        page = self.open_site(release_total=103)
        page.get_by_role('textbox', name='アーティスト名').fill('ジェフ・ベック')
        page.get_by_role('button', name='検索', exact=True).tap()
        page.get_by_role('button', name='この名義の作品を見る →').tap()
        section = page.locator('#official-releases')
        expect(section.locator('article')).to_have_count(2)
        section.get_by_text('収録曲・曲順・リンクを確認', exact=True).first.tap()
        section.get_by_role('button', name='曲目を取得', exact=True).first.tap()
        expect(section).to_contain_text('1. <Song>')
        section.get_by_role('button', name='さらに発売記録を読み込む', exact=True).tap()
        expect(section).to_contain_text('6 / 103件取得')
        for control in section.locator('button:visible, a:visible, summary:visible').all():
            self.assertGreaterEqual(control.bounding_box()['height'], 44)
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))

    def test_pending_tracks_survive_an_unrelated_rerender(self):
        page = self.open_site()
        self.search(page)
        pending = []
        page.route('**/release/official?**', lambda route: pending.append(route))
        section = page.locator('#official-releases')
        section.get_by_text('収録曲・曲順・リンクを確認', exact=True).first.click()
        with page.expect_request('**/release/official?**'):
            section.get_by_role('button', name='曲目を取得', exact=True).first.click()
        page.evaluate('render()')
        self.assertEqual(len(pending), 1)
        pending[0].fulfill(json={'media': [{'position': 1, 'tracks': [{'position': 1, 'title': 'Delayed song'}]}]})
        expect(section).to_contain_text('1. Delayed song')
        expect(section.locator('.edition-tracks')).to_have_count(1)

    def test_legacy_pagination_and_related_bands_survive_updates(self):
        page = self.open_site(release_total=103)
        page.route('**/ws/2/release-group?**', lambda route: route.fulfill(json={'release-groups': [{'id': GROUP, 'title': 'supported', 'primary-type': 'Album'}], 'release-group-count': 103}))
        self.search(page)
        expect(page.locator('#related-bands')).to_be_visible()
        page.get_by_text('参考資料：MusicBrainzの作品一覧（配信未確認）', exact=True).click()
        more = page.get_by_role('button', name='さらに作品を読み込む', exact=True)
        expect(more).to_be_enabled()
        more.click()
        page.wait_for_function('offset === 2 && !busy')
        expect(page.locator('#status')).to_contain_text('取得済み1件')
        expect(more).to_be_enabled()
        expect(page.locator('#related-bands')).to_be_visible()

    def test_loaded_tracks_survive_pagination_and_show_failure(self):
        page = self.open_site(release_total=103)
        self.search(page)
        section = page.locator('#official-releases')
        details = section.locator('details').first
        details.get_by_text('収録曲・曲順・リンクを確認', exact=True).click()
        details.get_by_role('button', name='曲目を取得', exact=True).click()
        expect(details).to_contain_text('1. <Song>')
        section.get_by_role('button', name='さらに発売記録を読み込む', exact=True).click()
        expect(section).to_contain_text('6 / 103件取得')
        expect(section.locator('details').first).to_have_attribute('open', '')
        expect(section.locator('details').first).to_contain_text('1. <Song>')
        page.route('**/release/missing-label?**', lambda route: route.fulfill(status=403, json={}))
        details = section.locator('details').nth(1)
        details.get_by_text('収録曲・曲順・リンクを確認', exact=True).click()
        details.get_by_role('button', name='曲目を取得', exact=True).click()
        expect(details).to_contain_text('曲目を取得できませんでした：音楽データを取得できませんでした（403）')
        expect(details.get_by_role('button', name='曲目の取得を再試行')).to_be_enabled()

    def test_search_generated_evidence_and_track_comparison(self):
        page = self.open_site()
        section = self.search(page)
        supported = section.locator('article').filter(has=page.locator('.album-title', has_text='supported')).first
        expect(supported.locator('.availability').first).to_contain_text('根拠あり')
        expect(section.locator('article').filter(has=page.locator('.album-title', has_text='different')).locator('.availability').first).to_contain_text('不一致')
        for state in ('insufficient', 'stale', 'unverified'):
            expect(section.locator('article').filter(has=page.locator('.album-title', has_text=state)).locator('.availability').first).to_contain_text('情報不足')
        expect(supported.get_by_role('link', name='YouTube Musicでアルバムを開く')).to_have_attribute('href', 'https://music.youtube.com/browse/MPREb_supported')
        supported.get_by_text('自動照合の根拠を見る', exact=True).click()
        expect(supported.get_by_text('YouTube Music レーベル：Label · 発売元：Publisher', exact=True)).to_be_visible()
        supported.get_by_text('取得した曲目を比較', exact=True).click()
        expect(supported.get_by_text('1. YouTube Music：One / MusicBrainz：One', exact=False)).to_be_visible()
        expect(supported.get_by_role('link', name='発売盤の出典')).to_have_attribute('href', 'https://musicbrainz.org/release/' + GROUP)
        supported.get_by_text('従来の照合記録：', exact=False).click()
        expect(supported.get_by_text('配信レーベル：Legacy Label', exact=False)).to_be_visible()

    def test_catalog_remains_visible_when_musicbrainz_fails(self):
        page = self.open_site(fail_mb=True)
        section = self.search(page)
        expect(section.locator('article')).to_have_count(5)
        expect(page.locator('#status')).to_contain_text('403')

    def test_japanese_alias_and_existing_sort_controls(self):
        page = self.open_site()
        requests = []
        page.on('request', lambda request: requests.append(request.url))
        page.get_by_role('textbox', name='アーティスト名').fill('マイルス・デイヴィス')
        page.get_by_role('button', name='検索', exact=True).click()
        page.get_by_role('button', name='この名義の作品を見る →').click()
        expect(page.locator('#status')).to_contain_text('作品を表示しています')
        page.get_by_text('以前のYouTube Music一覧・保存記録・照合ツール', exact=True).click()
        section = page.locator('#results > details > section').first
        expect(section.locator('article')).to_have_count(5)
        self.assertTrue(any('query=Miles%20Davis' in url for url in requests))
        section.get_by_role('button', name='発売年順', exact=True).click()
        expect(section.get_by_role('button', name='発売年順', exact=True)).to_have_class('filter active')
        section.get_by_role('button', name='アルバム名順', exact=True).click()
        expect(section.get_by_role('button', name='アルバム名順', exact=True)).to_have_class('filter active')

    def test_mobile_layout_and_touch_targets(self):
        for width in (320, 375, 390, 430):
            with self.subTest(width=width):
                page = self.open_site(width)
                section = self.search(page)
                section.get_by_text('自動照合の根拠を見る', exact=True).first.click()
                section.get_by_text('取得した曲目を比較', exact=True).first.click()
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
                for control in section.locator('.filter, .listen, summary:visible').all():
                    self.assertGreaterEqual(control.bounding_box()['height'], 44)

    def test_existing_storage_backup_and_restore(self):
        page = self.open_site()
        url = 'https://music.youtube.com/browse/MPREb_supported'
        records = {GROUP: {'mbReleaseGroup': GROUP, 'ytUrl': url, 'verdict': 'different',
                           'ytLabel': 'Old label', 'notes': 'Old notes', 'checkedAt': '2020-01-01',
                           'evidenceSnapshot': {'releases': [{'id': 'legacy-edition'}]}}}
        page.evaluate('data => {localStorage.setItem("recordVerificationV1",JSON.stringify(data));localStorage.setItem("recordVerifiedLinks",JSON.stringify({legacy:"keep"}));localStorage.setItem("recordAlbumStatuses",JSON.stringify({legacy:"confirmed"}))}', records)
        page.reload()
        section = self.search(page)
        expect(section.get_by_text('照合記録：別盤・不一致', exact=False).first).not_to_be_visible()  # inside optional manual details
        with page.expect_download() as pending:
            section.get_by_role('button', name='照合記録をバックアップ').click()
        backup = json.loads(Path(pending.value.path()).read_text())
        self.assertEqual(backup['records'], records)
        with page.expect_event('dialog') as dialog:
            section.locator('input[type=file]').set_input_files({'name': 'backup.json', 'mimeType': 'application/json', 'buffer': json.dumps(backup).encode()})
        dialog.value.accept()
        self.assertEqual(page.evaluate('JSON.parse(localStorage.getItem("recordVerifiedLinks"))'), {'legacy': 'keep'})
        self.assertEqual(page.evaluate('JSON.parse(localStorage.getItem("recordAlbumStatuses"))'), {'legacy': 'confirmed'})
        self.assertTrue(page.evaluate('Object.values(JSON.parse(localStorage.getItem("recordVerificationV1"))).some(r=>r.evidenceSnapshot.releases[0].id==="legacy-edition")'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
