"""Opt-in real MusicBrainz credits/recording relationships. No streaming requests."""
import datetime
import json
import time
from pathlib import Path
import requests

OUT = Path(__file__).resolve().parents[1] / 'docs' / 'v0.64'

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers['User-Agent'] = 'RECORD/0.64 (https://github.com/dqsh55-design/record)'
    report = {'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'mode': 'real HTTPS', 'artists': [], 'streaming_tested': False}
    def get(path, **params):
        for attempt in range(3):
            time.sleep(1.2 * (attempt + 1))
            r = session.get('https://musicbrainz.org/ws/2/' + path, params={'fmt': 'json', **params}, timeout=25)
            if r.status_code not in (429, 502, 503, 504):
                break
        r.raise_for_status()
        return r.json()
    def save(name, data):
        (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2))
    for name, aid, own, joint, guest_title, guest_artist in [
        ('Miles Davis', '561d854a-6a28-4aa7-8c99-323e6ce46c2a', 'Kind of Blue', 'Modern Jazz Trumpets', "Somethin’ Else", 'Cannonball Adderley'),
        ('Jeff Beck', '14a4bc78-1c2d-4ca7-8d1b-9b58076a2a17', 'Blow by Blow', 'Jeff Beck With the Jan Hammer Group Live', 'Amused to Death', 'Roger Waters')]:
        item = {'artist': name, 'artist_id': aid, 'index_pages': [], 'samples': []}
        prefix = name.replace(' ', '-')
        try:
            groups, offset = [], 0
            while True:
                d = get('release-group', artist=aid, type='album', inc='artist-credits', limit=100, offset=offset)
                batch = d['release-groups']
                item['index_pages'].append({'offset': offset, 'count': len(batch), 'total': d['release-group-count']})
                groups.extend(batch); offset += len(batch)
                if offset >= d['release-group-count']:
                    break
                if not batch:
                    raise ValueError('Empty index page')
            save(prefix + '-index.json', groups)
            def sample(group, label, check_performance=False):
                editions = get('release', **{'release-group': group['id'], 'inc': 'artist-credits+labels+media', 'limit': 100})
                release = next(r for r in editions['releases'] if r.get('status') == 'Official')
                data = get('release/' + release['id'], inc='recordings+labels+artist-credits+artist-rels+recording-level-rels')
                # Attach the separately fetched real group for replaying source precedence.
                data['release-group'] = group
                filename = prefix + '-' + label + '.json'
                save(filename, data)
                roles = []
                for m in data.get('media', []):
                    for t in m.get('tracks', []):
                        recording = t.get('recording', {})
                        for rel in recording.get('relations', []):
                            if rel.get('artist', {}).get('id') == aid and rel.get('type') in ('instrument', 'vocal', 'performer'):
                                roles.append({'recording_id': recording['id'], 'title': t.get('title'), 'type': rel['type'], 'attributes': rel.get('attributes', [])})
                item['samples'].append({'label': label, 'file': filename, 'group_id': group['id'], 'title': group['title'], 'release_id': release['id'], 'credits': data.get('artist-credit'), 'performance': roles, 'participation_expected': check_performance})
            for title, label in [(own, 'own'), (joint, 'joint')]:
                g = next(g for g in groups if g['title'] == title)
                sample(g, label)
            search = get('release-group', query='releasegroup:"' + guest_title + '" AND artist:"' + guest_artist + '"', limit=5)
            save(prefix + '-guest-search.json', search)
            guest = next(g for g in search['release-groups'] if g.get('primary-type') == 'Album')
            sample(guest, 'guest', True)
            relations = get('artist/' + aid, inc='artist-rels')
            save(prefix + '-artist-relations.json', relations)
        except (requests.RequestException, ValueError, StopIteration) as error:
            item['error'] = type(error).__name__ + ': ' + str(error)
        report['artists'].append(item)
        save('live-report.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
