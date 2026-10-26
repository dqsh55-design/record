"""Opt-in real browser connectivity/performance on a localhost copy; no deployment."""
import datetime
import functools
import http.server
import json
import os
from pathlib import Path
import shutil
import threading
import time
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'v0.65'

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    report = {'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'mode': 'real Chromium HTTPS from localhost', 'artists': [], 'streaming_playback_tested': False}
    try:
        with sync_playwright() as pw:
            executable = os.environ.get('RECORD_CHROMIUM') or shutil.which('chromium') or shutil.which('google-chrome')
            options = {'executable_path': executable} if executable else {}
            proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
            if proxy:
                options['proxy'] = {'server': proxy, 'bypass': '127.0.0.1,localhost'}
            browser = pw.chromium.launch(**options)
            for name in ('Miles Davis', 'Jeff Beck'):
                context = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
                page = context.new_page()
                item = {'artist': name, 'musicbrainz_responses': [], 'page_errors': [], 'request_failures': []}
                page.on('response', lambda r, item=item: item['musicbrainz_responses'].append({'url': r.url, 'status': r.status}) if r.url.startswith('https://musicbrainz.org/ws/2/') else None)
                page.on('requestfailed', lambda r, item=item: item['request_failures'].append({'url': r.url, 'failure': r.failure}))
                page.on('pageerror', lambda e, item=item: item['page_errors'].append(str(e)))
                try:
                    page.goto('http://127.0.0.1:' + str(server.server_port) + '/')
                    page.get_by_role('textbox', name='アーティスト名').fill(name)
                    started = time.monotonic()
                    page.get_by_role('button', name='検索', exact=True).click()
                    page.get_by_role('button', name='この名義の作品を見る →').first.click(timeout=30000)
                    selected = time.monotonic()
                    card = page.locator('#official-releases article').first
                    expect(card).to_be_visible(timeout=45000)
                    item.update(search_to_first_card_seconds=round(time.monotonic()-started, 3), selection_to_first_card_seconds=round(time.monotonic()-selected, 3), first_title=card.locator('.album-title').inner_text(), first_year=card.locator('.meta').inner_text(), card_y=round(card.bounding_box()['y'], 1))
                    item.update(page.evaluate("({source:chronology.mode,confirmed_index_groups:chronology.groups.length,all_ranges_fetched:chronology.allReady,edition_records:officialReleases.length,horizontal_overflow:document.documentElement.scrollWidth>innerWidth,order:chronologyOrder,scope:creditScope})"))
                    page.screenshot(path=str(OUT / (name.replace(' ', '-') + '-live-390.png')))
                except Exception as error:
                    item['error'] = type(error).__name__ + ': ' + str(error)[:400]
                    item['status_message'] = page.locator('#status').inner_text()
                report['artists'].append(item)
                context.close()
                (OUT / 'live-browser.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
            browser.close()
    finally:
        server.shutdown()
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
