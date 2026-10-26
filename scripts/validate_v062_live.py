"""Opt-in connectivity checks; no blocked destination or access bypass.

Run with requests installed: python scripts/validate_v062_live.py
Reports search connectivity separately from verified album metadata.
"""
import datetime
import json
import time
from pathlib import Path
import requests


def main():
    out = Path(__file__).resolve().parents[1] / 'docs' / 'v0.62'
    out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers['User-Agent'] = 'RECORD/0.62 (https://github.com/dqsh55-design/record)'
    report = {'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'targets': [], 'direct_album_verified': False, 'bypass_attempted': False}
    youtube_blocked = False
    for name, artist in [('Jeff Beck', '14a4bc78-1c2d-4ca7-8d1b-9b58076a2a17'),
                         ('Miles Davis', '561d854a-6a28-4aa7-8c99-323e6ce46c2a')]:
        item = {'artist': name, 'artist_id': artist}
        try:
            for attempt in range(3):
                time.sleep(1.2 * (attempt + 1))
                response = session.get('https://musicbrainz.org/ws/2/release', params={
                    'artist': artist, 'inc': 'labels+release-groups+media', 'limit': 100, 'fmt': 'json'}, timeout=20)
                if response.status_code not in (429, 502, 503):
                    break
            item['musicbrainz_status'] = response.status_code
            response.raise_for_status()
            data = response.json()
            item.update(total=data['release-count'], fetched=len(data['releases']))
            albums = [r for r in data['releases'] if r.get('status') == 'Official' and r.get('release-group', {}).get('primary-type') == 'Album']
            item['official_albums'] = len(albums)
            release = next((r for r in albums if r.get('cover-art-archive', {}).get('front')), None)
            if release:
                time.sleep(1.2)
                detail = session.get('https://musicbrainz.org/ws/2/release/' + release['id'], params={'inc': 'recordings+labels+artist-credits+release-groups', 'fmt': 'json'}, timeout=20)
                item['edition_detail_status'] = detail.status_code
                detail.raise_for_status()
                (out / (name.replace(' ', '-') + '-edition.json')).write_text(json.dumps(detail.json(), ensure_ascii=False, indent=2))
                cover = session.get('https://coverartarchive.org/release/' + release['id'] + '/front-250', timeout=20, allow_redirects=False)
                item['cover'] = {'release_id': release['id'], 'status': cover.status_code,
                                 'redirect': cover.headers.get('location'), 'redirect_followed': False,
                                 'image_received': cover.status_code == 200 and cover.headers.get('content-type', '').startswith('image/')}
        except requests.RequestException as error:
            item['musicbrainz_or_cover_error'] = type(error).__name__
        if youtube_blocked:
            item['youtube_music'] = {'skipped': 'Earlier normal connection was denied; no repeated access or workaround.'}
        else:
            try:
                response = session.get('https://music.youtube.com/search', params={'q': name}, timeout=20, allow_redirects=False)
                item['youtube_music'] = {'status': response.status_code, 'album_metadata_verified': False}
                youtube_blocked = response.status_code in (401, 403, 429)
            except requests.RequestException as error:
                item['youtube_music'] = {'error': type(error).__name__, 'proxy_tunnel_status': 403 if '403 Forbidden' in str(error) else None, 'upstream_status_unconfirmed': True}
                youtube_blocked = True
        report['targets'].append(item)
    (out / 'live-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
