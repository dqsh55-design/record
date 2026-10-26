"""Opt-in real MusicBrainz requests; full lightweight index, bounded edition samples."""
import datetime
import json
import time
from pathlib import Path
import requests

OUT = Path(__file__).resolve().parents[1] / 'docs' / 'v0.63'

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers['User-Agent'] = 'RECORD/0.63 (https://github.com/dqsh55-design/record)'
    report = {'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'mode': 'real HTTP', 'artists': [], 'youtube_playback_tested': False}
    def get(path, **params):
        for attempt in range(3):
            time.sleep(1.2 * (attempt + 1))
            r = session.get('https://musicbrainz.org/ws/2/' + path, params={'fmt': 'json', **params}, timeout=25)
            if r.status_code not in (429, 502, 503, 504):
                break
        r.raise_for_status()
        return r.json()
    for name, artist in [('Miles Davis', '561d854a-6a28-4aa7-8c99-323e6ce46c2a'), ('Jeff Beck', '14a4bc78-1c2d-4ca7-8d1b-9b58076a2a17')]:
        item = {'artist': name, 'artist_id': artist, 'index_pages': [], 'edition_pages': []}
        try:
            groups, offset = [], 0
            while True:
                d = get('release-group', artist=artist, type='album', limit=100, offset=offset)
                item['index_pages'].append({'offset': offset, 'count': len(d['release-groups']), 'total': d['release-group-count']})
                groups.extend(d['release-groups']); offset += len(d['release-groups'])
                if offset >= d['release-group-count']:
                    break
                if not d['release-groups']:
                    raise ValueError('Empty page before completion')
            groups = list({g['id']: g for g in groups}.values())
            groups.sort(key=lambda g: (not bool(g.get('first-release-date')), g.get('first-release-date', ''), g['id']))
            (OUT / (name.replace(' ', '-') + '-index.json')).write_text(json.dumps(groups, ensure_ascii=False, indent=2))
            item.update(unique_groups=len(groups), unknown_year=sum(not g.get('first-release-date') for g in groups))
            # Oldest, newest and a familiar work; two edition pages at most each.
            samples = [groups[0], next(g for g in reversed(groups) if g.get('first-release-date'))]
            title = 'Kind of Blue' if name == 'Miles Davis' else 'Blow by Blow'
            familiar = next((g for g in groups if g['title'] == title), None)
            if familiar and familiar not in samples:
                samples.append(familiar)
            for g in samples:
                offset = 0
                for page in range(2):
                    d = get('release', **{'release-group': g['id'], 'inc': 'labels+media', 'limit': 100, 'offset': offset})
                    item['edition_pages'].append({'group': g['id'], 'title': g['title'], 'original_date': g.get('first-release-date'), 'offset': offset, 'count': len(d['releases']), 'total': d['release-count'], 'official': sum(r.get('status') == 'Official' for r in d['releases'])})
                    (OUT / (name.replace(' ', '-') + '-' + g['id'] + '-' + str(offset) + '.json')).write_text(json.dumps(d, ensure_ascii=False, indent=2))
                    offset += len(d['releases'])
                    if offset >= d['release-count']:
                        break
        except (requests.RequestException, ValueError) as error:
            item['error'] = str(error)
        report['artists'].append(item)
    (OUT / 'live-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
