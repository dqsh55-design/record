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
from automatic_matching import verify_album

GROUP = '11111111-1111-1111-1111-111111111111'
ROOT = Path(__file__).resolve().parents[1]


def generated_catalog():
    detail = {'title': 'Album', 'year': '2001', 'artists': [{'name': 'Artist'}], 'label': 'Label',
              'publisher': 'Publisher', 'description': 'Long description: ' + 'x' * 500,
              'trackCount': 2, 'tracks': [{'title': 'One'}, {'title': 'Two'}]}
    release = {'id': GROUP, 'date': '2001', 'title': 'Album', 'status': 'Official',
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
        # Recorded date windows are from 2026. Keep Date.now real for evidence expiry.
        context.add_init_script('window.NativeIntersectionObserver = window.IntersectionObserver; window.IntersectionObserver = undefined; Date.prototype.getUTCFullYear = () => 2026')
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
                    request.fulfill(json={'release-groups': [{'id': GROUP, 'title': 'supported', 'primary-type': 'Album', 'artist-credit': [{'artist': {'id': GROUP, 'name': 'Artist'}}], 'first-release-date': '2001'}], 'release-group-count': 1})
                else:
                    request.fulfill(json={'relations': []})
            else:
                request.fulfill(status=404, body='')

        page.route('**/*', route)
        page.goto('http://record.test' + base_path + '/')
        # Only intercepted mock traffic is used here; avoid real API pacing in the harness.
        page.evaluate('()=>{globalThis.realApi=api;api=(path,options)=>{lastRequestAt=0;return realApi(path,options)}}')
        return page

    def search(self, page):
        page.get_by_role('textbox', name='アーティスト名').fill('Artist')
        page.get_by_role('button', name='検索', exact=True).click()
        page.get_by_role('button', name='この名義の作品を見る →').click()
        expect(page.locator('#status')).not_to_contain_text('アルバムを取得します', timeout=20000)
        expect(page.locator('#status')).not_to_contain_text('作品を読み込んでいます')
        # Existing provenance/link tests include deliberately different artist IDs.
        page.get_by_role('combobox', name='名義', exact=True).select_option('all')
        page.get_by_text('設定・詳細', exact=True).click()
        page.get_by_text('以前のYouTube Music一覧・保存記録・照合ツール', exact=True).click()
        return page.locator('#historical-catalog > section').first

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
            {'id': id, 'title': 'Album', 'date': '2001', 'status': 'Official', 'release-group': {'primary-type': 'Album'}} for id in (GROUP, 'different-edition')]}))
        self.search(page)
        section = page.locator('#official-releases')
        expect(section.get_by_role('link', name='YouTube Musicで聴く')).to_have_count(1)
        expect(section.get_by_role('link', name='YouTube Musicで探す ↗')).to_have_count(1)
        section.get_by_text('収録曲・曲順・リンクを確認', exact=True).first.click()
        expect(section).to_contain_text('一致した曲目：One / Two')
        page.evaluate("ytAlbums.forEach(a=>{if(a.automatic_verification)a.automatic_verification.checked_at='2000-01-01'});render()")
        expect(section.get_by_role('link', name='YouTube Musicで聴く')).to_have_count(0)

    def test_v062_jeff_and_miles_real_editions_with_mock_youtube(self):
        # MB details are captured from live requests; YouTube metadata is synthetic.
        # This proves matching/rendering and does not establish a real streaming URL.
        for name in ('Jeff Beck', 'Miles Davis'):
            with self.subTest(artist=name):
                release = json.loads((ROOT / 'docs/v0.62' / (name.replace(' ', '-') + '-edition.json')).read_text())
                tracks = [t for m in sorted(release['media'], key=lambda m: m['position']) for t in sorted(m['tracks'], key=lambda t: t['position'])]
                detail = {'title': release['title'], 'year': release['date'][:4], 'trackCount': len(tracks),
                          'artists': [{'name': a.get('name') or a['artist']['name']} for a in release['artist-credit'] if isinstance(a, dict)],
                          'tracks': [{'title': t['title']} for t in tracks], 'label': release['label-info'][0]['label']['name']}
                album = {'id': 'MPREb_mock' + name.replace(' ', ''), 'title': release['title'], 'artist_check': 'matched'}
                album['url'] = 'https://music.youtube.com/browse/' + album['id']
                mb = Mock()
                mb.get.side_effect = lambda path, release=release, **kw: {'releases': [{'id': release['id']}], 'count': 1} if path == 'release/' else release
                album['automatic_verification'] = verify_album(album, Mock(get_album=lambda id: detail), mb)
                self.assertEqual(album['automatic_verification']['status'], 'supported')
                page = self.open_site(390)
                page.route('**/ws/2/artist?**', lambda route, request, name=name: route.fulfill(json={'artists': [{'id': GROUP, 'name': name, 'type': 'Person'}]}))
                page.route('**/ws/2/release?**', lambda route, request, release=release: route.fulfill(json={'releases': [release], 'release-count': 1}))
                page.route('**/ws/2/release/*?**', lambda route, request, release=release: route.fulfill(json=release))
                page.route('**/data/ytmusic-albums.json', lambda route, request, name=name, album=album: route.fulfill(json={name: [album]}))
                page.reload()
                page.get_by_role('textbox', name='アーティスト名').fill(name)
                page.get_by_role('button', name='検索', exact=True).click()
                page.get_by_role('button', name='この名義の作品を見る →').click()
                section = page.locator('#official-releases')
                section.get_by_role('combobox', name='名義', exact=True).select_option('all')
                expect(section.get_by_role('link', name='YouTube Musicで聴く')).to_have_attribute('href', album['url'])
                expect(section.locator('.album-label')).to_have_text('この盤のレーベル：' + detail['label'])
                expect(section.locator('.album-title')).to_have_text(release['title'])
                page.wait_for_function('!officialLoading')
                expect(section.locator('.edition-identity')).not_to_be_visible()
                output = os.environ.get('RECORD_SCREENSHOT_DIR')
                if output:
                    Path(output).mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(Path(output) / (name.replace(' ', '-') + '-390.png')), full_page=True)
                section.get_by_text('収録曲・曲順・リンクを確認', exact=True).click()
                section.get_by_role('button', name='曲目を取得', exact=True).click()
                expect(section.locator('.edition-tracks')).to_contain_text(tracks[0]['title'])
                expect(section.locator('.edition-tracks')).to_contain_text(tracks[-1]['title'])
                page.evaluate("ytAlbums[0].url='https://music.youtube.com/playlist?list=OLAK5uy_mock';render()")
                expect(section.get_by_role('link', name='YouTube Musicで聴く')).to_have_count(0)
                expect(section.get_by_role('link', name='YouTube Musicで探す ↗')).to_be_visible()

    def test_v062_card_provenance_is_in_details_and_cover_is_larger(self):
        for width in (320, 375, 390, 430):
            page = self.open_site(width)
            self.search(page)
            card = page.locator('#official-releases article').first
            card.scroll_into_view_if_needed()
            expect(card.locator('.album-title')).to_be_visible()
            expect(card.locator('.album-label')).to_have_text('この盤のレーベル：Epic')
            expect(card.locator('.meta')).to_have_text('2001年（初回発売）')
            expect(card.locator('.edition-identity')).not_to_be_visible()
            expect(card.locator('.link-state')).to_have_text('配信状況は未確認')
            self.assertGreaterEqual(card.locator('.cover').bounding_box()['width'], 76)
            card.get_by_text('収録曲・曲順・リンクを確認', exact=True).tap()
            expect(card.locator('.edition-identity')).to_be_visible()
            expect(card.get_by_role('link', name='発売記録を見る')).to_be_visible()
            self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))

    def test_v062_old_playlist_backup_is_preserved_without_promotion(self):
        page = self.open_site(fail_catalog=True)
        page.route('**/ws/2/release?**', lambda route: route.fulfill(json={'release-count': 1, 'releases': [
            {'id': GROUP, 'title': 'Edition', 'status': 'Official', 'release-group': {'primary-type': 'Album'}}]}))
        self.search(page)
        section = page.locator('#official-releases')
        backup = {'format': 'RECORD-verification-v1', 'records': {}, 'editionLinks': {GROUP: {'url': 'https://music.youtube.com/playlist?list=OLAK5uy_legacy', 'savedAt': '2026-01-01'}}}
        with page.expect_event('dialog') as dialog:
            page.locator('#settings-details').get_by_label('保存記録を復元').set_input_files({'name': 'old.json', 'mimeType': 'application/json', 'buffer': json.dumps(backup).encode()})
        dialog.value.accept()
        expect(section.get_by_role('link', name='YouTube Musicで聴く')).to_have_count(0)
        expect(section.get_by_role('link', name='YouTube Musicで探す ↗')).to_be_visible()
        section.get_by_text('収録曲・曲順・リンクを確認', exact=True).click()
        expect(section.get_by_role('link', name='保存したリンクを開く（利用者登録・未照合）')).to_have_attribute('href', backup['editionLinks'][GROUP]['url'])

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
        expect(section.get_by_role('link', name='保存したリンクを開く（利用者登録・未照合）')).to_have_attribute('href', 'https://music.youtube.com/browse/MPREb_edition')
        expect(section).not_to_contain_text('正規盤確認済み')
        with page.expect_download() as pending:
            page.locator('#settings-details').get_by_role('button', name='保存記録をバックアップ', exact=True).click()
        backup = json.loads(Path(pending.value.path()).read_text())
        self.assertEqual(backup['editionLinks'][GROUP]['source'], 'user')
        page.reload()
        self.search(page)
        section.get_by_text('収録曲・曲順・リンクを確認', exact=True).click()
        expect(section.get_by_role('link', name='保存したリンクを開く（利用者登録・未照合）')).to_be_visible()
        section.get_by_role('button', name='発売盤リンクを削除', exact=True).click()
        expect(section.get_by_role('link', name='YouTube Musicで探す ↗')).to_be_visible()
        with page.expect_event('dialog') as dialog:
            page.locator('#settings-details').get_by_label('保存記録を復元').set_input_files({'name': 'backup.json', 'mimeType': 'application/json', 'buffer': json.dumps(backup).encode()})
        dialog.value.accept()
        expect(section.get_by_role('link', name='保存したリンクを開く（利用者登録・未照合）')).to_be_visible()

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
        expect(page.locator('#catalog-info')).to_contain_text('発売盤 6件取得')
        expect(section.locator('article')).to_have_count(2)
        expect(section.get_by_role('link', name='YouTube Musicで探す ↗')).to_have_count(2)

    def test_release_failure_shows_retry_and_legacy_data(self):
        page = self.open_site(fail_release=True)
        self.search(page)
        section = page.locator('#official-releases')
        expect(section.get_by_role('alert')).to_contain_text('アルバムを読み込めませんでした', timeout=15000)
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
        # CI's normal font metrics produce a 17px line box: 17 + 2*13px padding = 43px.
        # Reproduce it regardless of the local browser's installed fonts.
        page.add_style_tag(content='.more { line-height:17px }')
        page.get_by_role('textbox', name='アーティスト名').fill('ジェフ・ベック')
        page.get_by_role('button', name='検索', exact=True).tap()
        page.get_by_role('button', name='この名義の作品を見る →').tap()
        section = page.locator('#official-releases')
        expect(section.locator('article')).to_have_count(2)
        section.get_by_text('収録曲・曲順・リンクを確認', exact=True).first.tap()
        section.get_by_role('button', name='曲目を取得', exact=True).first.tap()
        expect(section).to_contain_text('1. <Song>')
        more = section.get_by_role('button', name='さらに発売記録を読み込む', exact=True)
        self.assertGreaterEqual(more.bounding_box()['height'], 44, 'enabled pagination button')
        batch = page.evaluate('officialReleases')
        pending = []
        page.route('**/ws/2/release?**', lambda route: pending.append(route))
        with page.expect_request('**/ws/2/release?**'):
            more.tap()
        expect(more).to_be_disabled()
        self.assertGreaterEqual(more.bounding_box()['height'], 44, 'loading pagination button')
        self.assertEqual(len(pending), 1)
        pending[0].fulfill(json={'release-count': 103, 'releases': batch})
        expect(page.locator('#catalog-info')).to_contain_text('発売盤 6件取得')
        for control in section.locator('button:visible, a:visible, summary:visible, select:visible').all():
            self.assertGreaterEqual(control.bounding_box()['height'], 44, control.evaluate('(e)=>e.tagName+" "+(e.getAttribute("aria-label")||e.textContent).trim()'))
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
        # Main index is complete; legacy paginator retains its independent offset.
        self.search(page)
        expect(page.locator('#related-bands')).to_be_visible()
        page.route('**/ws/2/release-group?**', lambda route: route.fulfill(json={'release-groups': [{'id': GROUP, 'title': 'supported', 'primary-type': 'Album'}], 'release-group-count': 103}))
        page.evaluate('total=103;render()')
        page.get_by_text('参考資料：MusicBrainzの作品一覧（配信未確認）', exact=True).click()
        more = page.get_by_role('button', name='さらに作品を読み込む', exact=True)
        expect(more).to_be_enabled()
        more.click()
        page.wait_for_function('offset === 2 && !busy')
        self.assertEqual(page.evaluate('albums.length'), 1)
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
        expect(page.locator('#catalog-info')).to_contain_text('発売盤 6件取得')
        expect(section.locator('details').first).to_have_attribute('open', '')
        expect(section.locator('details').first).to_contain_text('1. <Song>')
        page.route('**/release/missing-label?**', lambda route: route.fulfill(status=403, json={}))
        details = section.locator('details').nth(1)
        details.get_by_text('収録曲・曲順・リンクを確認', exact=True).click()
        details.get_by_role('button', name='曲目を取得', exact=True).click()
        expect(details).to_contain_text('曲目を取得できませんでした：音楽データを取得できませんでした（403）')
        expect(details.get_by_role('button', name='曲目の取得を再試行')).to_be_enabled()

    def test_v063_chronological_prefix_and_scroll_for_both_artists(self):
        from urllib.parse import parse_qs
        for name in ('Miles Davis', 'Jeff Beck'):
            page = self.open_site(390)
            # Enable the real browser observer only for this scroll integration test.
            page.evaluate('()=>{window.IntersectionObserver = window.NativeIntersectionObserver}')
            groups = [{'id': 'later-' + str(i), 'title': 'Later', 'primary-type': 'Album', 'first-release-date': '2010'} for i in range(100)]
            groups += [{'id': 'old', 'title': 'Early', 'primary-type': 'Album', 'first-release-date': '1959'},
                       {'id': 'unknown', 'title': 'Unknown', 'primary-type': 'Album'}]
            for group in groups:
                group['artist-credit'] = [{'artist': {'id': 'artist', 'name': name}}]
            calls = []
            def api_route(route, request, calls=calls, groups=groups, name=name):
                url = urlparse(route.request.url)
                q = parse_qs(url.query)
                offset = int(q.get('offset', ['0'])[0])
                calls.append((url.path, offset, q.get('release-group', [''])[0], q.get('query', [''])[0]))
                if url.path.endswith('/release-group'):
                    route.fulfill(json={'release-group-count': len(groups), 'release-groups': groups[offset:offset + 100]})
                elif url.path.endswith('/release'):
                    group = q['release-group'][0]
                    if group == 'old':
                        editions = [{'id': 'old-' + str(i), 'title': name + ' early edition ' + str(i), 'status': 'Official', 'date': '2009', 'label-info': [{'label': {'name': 'Label'}}]} for i in range(105)]
                        # Overlap at the boundary must not duplicate a row.
                        batch = editions[:100] if offset == 0 else [editions[99]] + editions[100:]
                        route.fulfill(json={'release-count': 106, 'releases': batch})
                    else:
                        route.fulfill(json={'release-count': 1, 'releases': [{'id': group, 'title': group, 'status': 'Official', 'date': '2020'}]})
                else:
                    route.fulfill(json={'relations': []})
            page.route('**/ws/2/**', api_route)
            page.evaluate("chooseArtist({id:'artist',name:" + json.dumps(name) + "})")
            section = page.locator('#official-releases')
            expect(section.locator('article')).to_have_count(100, timeout=15000)
            self.assertEqual([c[1] for c in calls if not c[3]][:2], [0, 100])
            expect(section.locator('.decade').first).to_have_text('1950年代')
            expect(section.locator('.meta').first).to_have_text('1959年（初回発売）')
            expect(section.locator('article').first).to_contain_text('この盤の発売：2009')
            expect(section.locator('article').first.get_by_text('この盤の発売：2009', exact=False)).not_to_be_visible()
            self.assertFalse(section.locator('details').first.evaluate('(node)=>node.open'))
            page.evaluate("window.firstEdition=document.querySelector('#official-releases article')")
            page.locator('#chronology-more').scroll_into_view_if_needed()
            page.wait_for_function('officialReleases.length >= 105', timeout=15000)
            self.assertTrue(page.evaluate("firstEdition===document.querySelector('#official-releases article')"))
            self.assertEqual(section.locator('article[data-release-id="old-99"]').count(), 1)
            # Changing direction discards the prefix and starts at the newest known work.
            section.get_by_role('combobox', name='並び順', exact=True).select_option('desc')
            expect(section.locator('.decade').first).to_have_text('2010年代', timeout=10000)
            self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            # Unknown originals stay last in either direction and never borrow edition dates.
            self.assertEqual(page.evaluate("orderedGroups([{id:'u'},{id:'k','first-release-date':'1950'}]).map(g=>g.id)"), ['k', 'u'])
            page.close()

    def test_v064_credit_scopes_and_on_demand_performance(self):
        from urllib.parse import parse_qs
        page = self.open_site(390)
        credit = lambda id, name=None: {'artist': {'id': id, 'name': name or id}}
        groups = [{'id': kind, 'title': kind, 'primary-type': 'Album', 'first-release-date': str(1950 + i * 10),
                   'artist-credit': credits} for i, (kind, credits) in enumerate([
                       ('own', [credit('target')]), ('joint', [credit('other'), credit('target')]),
                       ('guest', [credit('other')]), ('unknown', []), ('band', [credit('band-id')])])]
        def route(route):
            url = urlparse(route.request.url)
            if url.path.endswith('/release-group'):
                route.fulfill(json={'release-groups': groups, 'release-group-count': len(groups)})
            elif url.path.endswith('/release'):
                group = next(g for g in groups if g['id'] == parse_qs(url.query)['release-group'][0])
                route.fulfill(json={'release-count': 1, 'releases': [{'id': group['id'], 'title': group['title'], 'status': 'Official',
                    'date': '2020', 'artist-credit': group['artist-credit'], 'label-info': [{'label': {'name': 'Label'}}]}]})
            elif url.path.endswith('/release/guest'):
                self.assertIn('recording-level-rels', parse_qs(url.query)['inc'][0])
                route.fulfill(json={'id': 'guest', 'artist-credit': [credit('other')], 'media': [{'position': 1, 'tracks': [
                    {'position': 1, 'title': 'Guest song', 'recording': {'id': 'recording-id', 'relations': [
                        {'type': 'instrument', 'artist': {'id': 'target'}, 'attributes': ['guitar']},
                        {'type': 'producer', 'artist': {'id': 'target'}}]}}]}]})
            else:
                route.fulfill(json={'relations': []})
        page.route('**/ws/2/**', route)
        page.evaluate("chooseArtist({id:'target',name:'Target'})")
        # Each interaction fetches only one work/page; all scopes reuse the same prefix.
        for _ in range(4):
            page.evaluate('loadOfficialReleases()')
        section = page.locator('#official-releases')
        expect(section.get_by_role('combobox', name='名義', exact=True)).to_have_value('credited')
        expect(section.locator('article')).to_have_count(2)
        expect(section.locator('.credit-badge').first).to_contain_text('本人名義')
        expect(section.locator('.credit-badge').nth(1)).to_contain_text('共同名義')
        section.get_by_role('combobox', name='名義', exact=True).select_option('joint')
        expect(section.locator('article')).to_have_count(1)
        expect(section.locator('.decade')).to_have_text('1960年代')
        section.get_by_role('combobox', name='名義', exact=True).select_option('pending')
        expect(section.locator('article')).to_have_count(3)
        guest = section.locator('article[data-release-id="guest"]')
        guest.locator('summary').click()
        expect(guest).to_contain_text('関連作品や所属バンドという理由だけでは参加と判定しません')
        guest.get_by_role('button', name='曲目を取得', exact=True).click()
        expect(guest.locator('.credit-badge')).to_contain_text('演奏参加')
        expect(guest.locator('.credit-evidence a[href*="/recording/"]')).to_have_attribute('href', 'https://musicbrainz.org/recording/recording-id')
        expect(page.locator('#credit-counts')).to_contain_text('演奏参加（録音の登録根拠あり） 1件')
        section.get_by_role('combobox', name='名義', exact=True).select_option('participation')
        expect(section.locator('article')).to_have_count(1)
        expect(page.locator('#catalog-info')).to_contain_text('参加作品の網羅性は保証しません')
        expect(section.locator('details')).to_have_attribute('open', '')
        section.get_by_role('combobox', name='名義', exact=True).select_option('credited')
        expect(section.locator('article')).to_have_count(2)
        section.get_by_role('combobox', name='並び順', exact=True).select_option('desc')
        page.wait_for_function('!officialLoading')
        # Newest work is a separate band credit: do not promote it to the target's solo albums.
        expect(section.locator('article')).to_have_count(0)
        section.get_by_role('combobox', name='名義', exact=True).select_option('pending')
        expect(section.locator('.album-title')).to_have_text('band')
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))

    def test_v064_captured_credit_and_band_routes_for_both_artists(self):
        # Every MB body below is captured real data, replayed offline.
        # The candidate index combines three chosen works to test an unrelated candidate;
        # it is not a claim that guest albums occur in the artist browse response.
        from urllib.parse import parse_qs
        report = json.loads((ROOT / 'docs/v0.64/live-report.json').read_text())
        for artist in report['artists']:
            prefix = artist['artist'].replace(' ', '-')
            releases = [json.loads((ROOT / 'docs/v0.64' / (prefix + '-' + kind + '.json')).read_text()) for kind in ('own', 'joint', 'guest')]
            groups = [r['release-group'] for r in releases]
            relationships = json.loads((ROOT / 'docs/v0.64' / (prefix + '-artist-relations.json')).read_text())
            page = self.open_site(375)
            def route(route, request, groups=groups, releases=releases, artist=artist, relationships=relationships):
                url = urlparse(route.request.url)
                q = parse_qs(url.query)
                if url.path.endswith('/release-group'):
                    items = groups if q.get('artist', [artist['artist_id']])[0] == artist['artist_id'] else []
                    route.fulfill(json={'release-group-count': len(items), 'release-groups': items})
                elif url.path.endswith('/release'):
                    release = next(r for r in releases if r['release-group']['id'] == q['release-group'][0])
                    route.fulfill(json={'release-count': 1, 'releases': [release]})
                elif '/release/' in url.path:
                    route.fulfill(json=next(r for r in releases if r['id'] == url.path.split('/')[-1]))
                else:
                    route.fulfill(json=relationships)
            page.route('**/ws/2/**', route)
            page.evaluate('chooseArtist(' + json.dumps({'id': artist['artist_id'], 'name': artist['artist']}) + ')')
            for _ in range(2):
                page.evaluate('loadOfficialReleases()')
            section = page.locator('#official-releases')
            expect(section.locator('article')).to_have_count(2)
            expect(section.locator('.credit-badge', has_text='本人名義')).to_have_count(1)
            expect(section.locator('.credit-badge', has_text='共同名義')).to_have_count(1)
            section.get_by_role('combobox', name='名義', exact=True).select_option('pending')
            expect(section.locator('article')).to_have_count(1)
            expect(section.locator('.album-title')).to_have_text(releases[2]['title'])
            section.locator('summary').click()
            section.get_by_role('button', name='曲目を取得', exact=True).click()
            expect(section.locator('.credit-badge')).to_contain_text('演奏参加')
            expect(section.get_by_role('combobox', name='名義', exact=True)).to_have_value('participation')
            self.assertGreater(section.locator('.credit-evidence a[href*="/recording/"]').count(), 0)
            expect(section.locator('details')).to_have_attribute('open', '')
            expect(section.get_by_role('link', name='YouTube Musicで探す ↗')).to_have_count(1)
            expect(page.locator('#related-bands')).to_be_visible()
            page.locator('#related-bands > summary').click()
            page.get_by_role('button', name='所属バンドを調べる →').click()
            band = next(rel['artist'] for rel in relationships['relations'] if rel['type'] == 'member of band' and rel.get('artist', {}).get('type') == 'Group')
            related = page.locator('#related-bands article').filter(has=page.get_by_text(band['name'], exact=True))
            expect(related).to_have_count(1)
            # A member's solo list does not absorb the band's works. The existing selector
            # opens that band's own artist ID and resets the previous list/scope.
            related.get_by_role('button', name='この名義の作品を見る →').click()
            page.wait_for_function('artistId === ' + json.dumps(band['id']) + ' && !officialLoading')
            expect(section.locator('h2')).to_have_text(band['name'] + ' の発売アルバム')
            expect(section.locator('article')).to_have_count(0)
            expect(section.get_by_role('combobox', name='名義', exact=True)).to_have_value('credited')
            self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            page.close()

    def test_v066_official_work_and_edition_evidence_stay_separate(self):
        # Real MB response replay; official sources are reviewed facts, not live calls.
        groups = ('6ccac9d2-22ed-33de-bd5d-f2aadcacf7f8',
                  '00fa7988-ba9e-4f50-8839-09a9d79a5e45',
                  'c67ed8da-fa12-433a-8f8a-a45c7bfe4d7b')
        editions = {}
        for group_id in groups:
            data = json.loads((ROOT / 'docs/v0.66' / (group_id + '-editions.json')).read_text())
            for release in data['releases']:
                editions[release['id']] = {**release, 'release-group': data['group']}
        selected = [editions[id] for id in (
            'c88138cf-00f3-3c70-8757-3bbe0e4713d1',
            'dd00e0df-dd7e-48af-8b13-921bf505167f',
            'c766c537-9eef-4005-ad35-b6b0a1bd5712',
            '608d22ac-be83-453e-97e8-6fc607a30908',
            '36469a3c-5ed7-460d-b2f8-c78208589fad',
            '93f9b391-3836-477e-bc3b-9d350684fb99')]
        refs = json.loads((ROOT / 'data/discography-references.json').read_text())
        for width in (320, 390, 430):
            page = self.open_site(width)
            pending = []
            page.route('**/data/discography-references.json', lambda route: pending.append(route))
            page.evaluate("items=>{artistId='985c709c-7771-4de3-9024-7bda29ebe3f9';artistName='Norah Jones';creditScope='all';officialReleases=[...items,items[0]];render();void loadDiscographyReferences()}", selected)
            section = page.locator('#official-releases')
            expect(section.locator('article')).to_have_count(6)
            expect(section.locator('.release-work')).to_have_count(3)
            expect(section.locator('.release-work').first).to_contain_text('4発売盤')
            original = section.locator('article').first
            original.locator('summary').click()
            field = original.get_by_role('textbox', name='Come Away With Meの発売盤リンク')
            field.fill('https://music.youtube.com/browse/MPREb_draft')
            page.evaluate("window.evidenceCard=document.querySelector('#official-releases article')")
            expect(original.locator('.discography-evidence')).to_contain_text('未確認')
            page.wait_for_function('discographyReferenceTask !== null')
            self.assertEqual(len(pending), 1)
            pending[0].fulfill(json=refs)
            expect(original.locator('.discography-evidence')).to_contain_text('照合済み')
            self.assertTrue(page.evaluate("evidenceCard===document.querySelector('#official-releases article')"))
            expect(field).to_have_value('https://music.youtube.com/browse/MPREb_draft')
            expect(field).to_be_focused()
            expect(original.locator('.discography-evidence')).not_to_contain_text('ユニバーサル ミュージック合同会社')
            reissue = section.locator('article[data-release-id="dd00e0df-dd7e-48af-8b13-921bf505167f"]')
            reissue.locator('summary').click()
            expect(reissue.locator('.discography-evidence')).to_contain_text('正規再発盤')
            expect(reissue.locator('.discography-evidence')).to_contain_text('この盤の発売元（公式資料）：ユニバーサル ミュージック合同会社')
            expect(reissue.locator('.meta')).to_have_text('2002年（初回発売）')
            expect(reissue.locator('.edition-release-meta')).to_contain_text('この盤の発売：2022-05-27')
            expect(reissue.locator('.album-label')).to_have_text('この盤のレーベル：Blue Note')
            expect(reissue.get_by_role('link', name='公式資料を見る ↗')).to_have_count(2)
            expect(section.locator('article[data-release-id="608d22ac-be83-453e-97e8-6fc607a30908"]')).to_contain_text('確認待ち')
            # A newer detail can change the status/label without replacing the work year or URL draft.
            detail = {**selected[0], 'date': '2030', 'status': None, 'label-info': [], 'media': []}
            page.route('**/ws/2/release/c88138cf-00f3-3c70-8757-3bbe0e4713d1?**', lambda route: route.fulfill(json=detail))
            original.get_by_role('button', name='曲目を取得', exact=True).click()
            expect(original.locator('.edition-release-meta')).to_contain_text('確認待ち')
            expect(original.locator('.edition-release-meta')).to_contain_text('この盤の発売：2030')
            expect(original.locator('.meta')).to_have_text('2002年（初回発売）')
            expect(original.locator('.album-label')).to_have_text('レーベル未登録')
            expect(field).to_have_value('https://music.youtube.com/browse/MPREb_draft')
            self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            page.close()

    def test_v065_first_screen_with_real_window_snapshots(self):
        # Real recorded MB bodies replayed in a mobile browser: NOT a live speed test.
        from urllib.parse import parse_qs
        import time
        for name, aid in [('Miles Davis', '561d854a-6a28-4aa7-8c99-323e6ce46c2a'), ('Jeff Beck', '14a4bc78-1c2d-4ca7-8d1b-9b58076a2a17')]:
            prefix = name.replace(' ', '-')
            window = json.loads((ROOT / 'docs/v0.65' / (prefix + '-window-0.json')).read_text())
            editions = json.loads((ROOT / 'docs/v0.65' / (prefix + '-first-editions.json')).read_text())
            for width in (320, 375, 390, 430):
                page = self.open_site(width)
                pending, catalogs, calls = [], [], []
                def route(route, request, window=window, editions=editions, pending=pending, calls=calls):
                    url = urlparse(route.request.url)
                    q = parse_qs(url.query)
                    calls.append((url.path, q))
                    if url.path.endswith('/release-group'):
                        pending.append(route)
                    elif url.path.endswith('/release'):
                        route.fulfill(json=editions)
                    else:
                        route.fulfill(json={'relations': []})
                page.route('**/ws/2/**', route)
                page.route('**/data/ytmusic-albums.json', lambda route, request, catalogs=catalogs: catalogs.append(route))
                page.evaluate('()=>{globalThis.catalogDone=false;globalThis.catalogLoad=loadListeningCatalog;loadListeningCatalog=async artist=>{await catalogLoad(artist);catalogDone=true}}')
                with page.expect_request('**/ws/2/release-group?**'):
                    page.evaluate('void chooseArtist(' + json.dumps({'id': aid, 'name': name}) + ')')
                section = page.locator('#official-releases')
                expect(section.get_by_role('combobox', name='並び順')).to_have_value('asc')
                expect(section.get_by_role('combobox', name='名義', exact=True)).to_have_value('credited')
                expect(section.get_by_role('progressbar')).to_be_visible()
                expect(section.locator('article')).to_have_count(0)
                expect(section.locator('.loading-card')).to_have_attribute('aria-hidden', 'true')
                self.assertEqual(len(pending), 1)
                pending[0].fulfill(json=window)
                expected = [r for r in editions['releases'] if r.get('status') not in ('Bootleg', 'Pseudo-Release', 'Promotion')]
                expect(section.locator('article')).to_have_count(len(expected))
                self.assertEqual(len(catalogs), 1)  # Slow optional catalog cannot hold the main list hostage.
                self.assertEqual(len(calls), 2)  # One complete small window + one edition page, no full browse.
                self.assertTrue('query' in calls[0][1])
                self.assertTrue(all('artist' not in q for _, q in calls))
                expect(section.locator('select:visible')).to_have_count(2)
                self.assertEqual(section.locator('#credit-scope option').count(), 6)
                expect(page.locator('#settings-details')).not_to_have_attribute('open', '')
                expect(page.get_by_role('button', name='保存記録をバックアップ', exact=True)).not_to_be_visible()
                expect(page.locator('#catalog-info')).not_to_be_visible()
                first = section.locator('article').first
                expect(first.locator('.album-title')).to_be_visible()
                expect(first.locator('.album-label')).to_be_visible()
                expect(first.locator('.credit-badge')).to_be_visible()
                expect(first.locator('.meta')).to_have_text('1951年（初回発売）' if name == 'Miles Davis' else '1972年（初回発売）')
                self.assertLess(first.bounding_box()['y'] + 150, 844)
                expect(first.locator('.link-state')).not_to_be_visible()
                expect(first.locator('.edition-identity')).not_to_be_visible()
                expect(first.locator('.release-detail').filter(has_text='この盤の発売：')).not_to_be_visible()
                for control in section.locator('select:visible, a:visible, summary:visible').all():
                    self.assertGreaterEqual(control.bounding_box()['height'], 44)
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
                for select in section.locator('select:visible').all():
                    self.assertGreaterEqual(select.evaluate('e=>parseFloat(getComputedStyle(e).fontSize)'), 16)
                # Actual distinct release IDs, including reissues, stay distinct.
                self.assertEqual(len(expected), len(set(section.locator('article').evaluate_all('(rows)=>rows.map(r=>r.dataset.releaseId)'))))
                page.evaluate("globalThis.primaryCard=document.querySelector('#official-releases article')")
                if width == 390:
                    first.locator('summary').click()
                    draft = first.get_by_role('textbox', name=expected[0]['title'] + 'の発売盤リンク')
                    draft.fill('https://music.youtube.com/browse/MPREb_draft')
                catalogs[0].fulfill(json={})
                page.wait_for_function('catalogDone && !officialLoading')
                self.assertTrue(page.evaluate("primaryCard===document.querySelector('#official-releases article')"))
                if width == 390:
                    expect(draft).to_have_value('https://music.youtube.com/browse/MPREb_draft')
                    expect(draft).to_be_focused()
                    first.locator('summary').click()
                output = os.environ.get('RECORD_SCREENSHOT_DIR')
                if output and width == 390:
                    Path(output).mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(Path(output) / (prefix + '-v065-390.png')))
                first.locator('summary').click()
                expect(first.locator('.edition-identity')).to_be_visible()
                expect(first.get_by_text('この盤の発売：', exact=False)).to_be_visible()
                page.get_by_text('設定・詳細', exact=True).click()
                page.get_by_text('一覧の情報・読み込み状況', exact=True).click()
                expect(page.locator('#catalog-info')).to_contain_text('全作品取得済みという意味ではありません')
                expect(page.get_by_role('button', name='保存記録をバックアップ', exact=True)).to_be_visible()
                page.close()

    def test_v065_partial_browse_fallback_and_retry(self):
        from urllib.parse import parse_qs
        page = self.open_site()
        target = 'target'
        def group(id, date):
            return {'id': id, 'title': id, 'primary-type': 'Album', 'first-release-date': date, 'artist-credit': [{'artist': {'id': target}}]}
        pending, queries, releases = [], [], []
        fail_release = [True]
        def route(route):
            url = urlparse(route.request.url)
            q = parse_qs(url.query)
            if url.path.endswith('/release-group'):
                if 'query' in q:
                    queries.append(route.request.url)
                    route.fulfill(status=503, json={})
                elif q.get('offset', ['0'])[0] == '0':
                    route.fulfill(json={'release-group-count': 101, 'release-groups': [group('later-' + str(i), '2000') for i in range(100)]})
                else:
                    pending.append(route)
            elif url.path.endswith('/release'):
                releases.append(q)
                if fail_release[0]:
                    route.fulfill(status=403, json={})
                else:
                    route.fulfill(json={'release-count': 1, 'releases': [{'id': 'edition', 'title': 'Earliest edition', 'status': 'Official', 'date': '2020'}]})
            else:
                route.fulfill(json={'relations': []})
        page.route('**/ws/2/**', route)
        page.evaluate("void chooseArtist({id:'target',name:'Target'})")
        page.wait_for_function('chronology.mode === "browse" && chronology.indexOffset === 100')
        page.wait_for_timeout(30)
        expect(page.locator('#official-releases article')).to_have_count(0)
        expect(page.get_by_role('progressbar')).to_have_attribute('value', '100')
        self.assertEqual(len(queries), 1)  # Cold search fails fast, bounded fallback is available.
        self.assertEqual(len(pending), 1)
        pending[0].fulfill(json={'release-group-count': 101, 'release-groups': [group('oldest', '1950')]})
        section = page.locator('#official-releases')
        expect(section.get_by_role('alert')).to_contain_text('読み込めませんでした')
        expect(page.locator('#catalog-info')).to_contain_text('403')
        expect(section.get_by_role('button', name='発売記録の取得を再試行')).to_be_enabled()
        fail_release[0] = False
        section.get_by_role('button', name='発売記録の取得を再試行').click()
        expect(section.locator('.meta')).to_have_text('1950年（初回発売）')
        self.assertEqual(len(releases), 2)
        self.assertEqual([q['offset'][0] for q in releases], ['0', '0'])
        expect(section.get_by_role('alert')).to_have_count(0)

    def test_v065_menu_change_during_pending_window_discards_old_response(self):
        from urllib.parse import parse_qs
        page = self.open_site()
        pending = []
        def route(route):
            url = urlparse(route.request.url)
            q = parse_qs(url.query)
            if url.path.endswith('/release-group'):
                if 'TO 1979' in q['query'][0]:
                    pending.append(route)
                else:
                    route.fulfill(json={'count': 1, 'release-groups': [{'id': 'new', 'title': 'Newest', 'primary-type': 'Album', 'first-release-date': '2024', 'artist-credit': [{'artist': {'id': 'target'}}]}]})
            elif url.path.endswith('/release'):
                route.fulfill(json={'release-count': 1, 'releases': [{'id': 'new-edition', 'title': 'Newest', 'status': 'Official'}]})
            else:
                route.fulfill(json={'relations': []})
        page.route('**/ws/2/**', route)
        with page.expect_request('**/release-group?**'):
            page.evaluate("void chooseArtist({id:'target',name:'Target'})")
        page.get_by_role('combobox', name='並び順').select_option('desc')
        pending[0].fulfill(json={'count': 1, 'release-groups': [{'id': 'old', 'title': 'Old', 'primary-type': 'Album', 'first-release-date': '1950', 'artist-credit': [{'artist': {'id': 'target'}}]}]})
        expect(page.locator('#official-releases .album-title')).to_have_text('Newest')
        expect(page.get_by_role('combobox', name='並び順')).to_have_value('desc')
        expect(page.locator('#official-releases .meta')).to_have_text('2024年（初回発売）')

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
        expect(page.locator('#results')).to_contain_text('403')

    def test_japanese_alias_and_existing_sort_controls(self):
        page = self.open_site()
        requests = []
        page.on('request', lambda request: requests.append(request.url))
        page.get_by_role('textbox', name='アーティスト名').fill('マイルス・デイヴィス')
        page.get_by_role('button', name='検索', exact=True).click()
        page.get_by_role('button', name='この名義の作品を見る →').click()
        page.wait_for_function('!officialLoading')
        page.get_by_text('設定・詳細', exact=True).click()
        page.get_by_text('以前のYouTube Music一覧・保存記録・照合ツール', exact=True).click()
        section = page.locator('#historical-catalog > section').first
        expect(section.locator('article')).to_have_count(5)
        self.assertTrue(any('query=Miles%20Davis' in url for url in requests))
        section.get_by_role('button', name='発売年順', exact=True).click()
        expect(section.get_by_role('button', name='発売年順', exact=True)).to_have_class('filter active')
        section.get_by_role('button', name='アルバム名順', exact=True).click()
        expect(section.get_by_role('button', name='アルバム名順', exact=True)).to_have_class('filter active')

    def test_norah_japanese_search_variants(self):
        for query in ['ノラジョーンズ', 'ノラ・ジョーンズ', 'ノラ ジョーンズ']:
            page = self.open_site()
            requests = []
            page.on('request', lambda request: requests.append(request.url))
            page.get_by_role('textbox', name='アーティスト名').fill(query)
            page.get_by_role('button', name='検索', exact=True).click()
            expect(page.get_by_role('button', name='この名義の作品を見る →')).to_be_visible()
            self.assertTrue(any('query=Norah%20Jones' in url for url in requests))

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
