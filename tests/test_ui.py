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

    def open_site(self, width=390, fail_mb=False, fail_catalog=False, fail_release=False, release_total=3):
        context = self.browser.new_context(viewport={'width': width, 'height': 844}, is_mobile=width < 500, has_touch=width < 500)
        self.addCleanup(context.close)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        self.addCleanup(lambda: self.assertEqual(errors, []))

        def route(request):
            url = urlparse(request.request.url)
            if url.hostname == 'record.test' and url.path == '/':
                request.fulfill(body=(ROOT / 'index.html').read_text(), content_type='text/html')
            elif url.path == '/data/ytmusic-albums.json':
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
        page.goto('http://record.test/')
        return page

    def search(self, page):
        page.get_by_role('textbox', name='アーティスト名').fill('Artist')
        page.get_by_role('button', name='検索', exact=True).click()
        page.get_by_role('button', name='この名義の作品を見る →').click()
        expect(page.locator('#status')).not_to_contain_text('アルバムを取得します', timeout=20000)
        expect(page.locator('#status')).not_to_contain_text('作品を読み込んでいます')
        page.get_by_text('以前のYouTube Music一覧・保存記録・照合ツール', exact=True).click()
        return page.locator('#results > details > section').first

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
        section.get_by_text('収録曲・曲順を見る', exact=True).first.click()
        section.get_by_role('button', name='曲目を取得', exact=True).first.click()
        expect(section).to_contain_text('1. <Song>')
        expect(section).to_contain_text('EPC 1')

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
