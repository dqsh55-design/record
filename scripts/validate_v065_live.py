"""Real HTTPS: compare a complete first date window against a full browse index.

This diagnostic does not deploy, change catalog data, or test streaming playback.
"""
import datetime
import argparse
import json
import time
from pathlib import Path
import requests

OUT = Path(__file__).resolve().parents[1] / 'docs' / 'v0.65'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artist', choices=['Miles Davis', 'Jeff Beck'])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers['User-Agent'] = 'RECORD/0.65 (https://github.com/dqsh55-design/record)'
    report = {'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'mode': 'real HTTPS', 'artists': [], 'streaming_tested': False}
    if args.artist and (OUT / 'live-report.json').exists():
        prior = json.loads((OUT / 'live-report.json').read_text())
        for artist in prior['artists']:
            if artist['artist'] != args.artist:
                artist.setdefault('checked_at', prior['checked_at'])
                report['artists'].append(artist)
    previous = 0
    def get(path, **params):
        nonlocal previous
        for attempt in range(3):
            time.sleep(max(0, 1.1 - (time.monotonic() - previous)))
            previous = time.monotonic()
            response = session.get('https://musicbrainz.org/ws/2/' + path, params={'fmt': 'json', **params}, timeout=25)
            if response.status_code not in (429, 502, 503, 504):
                break
            time.sleep(1.7 * (attempt + 1))
        response.raise_for_status()
        return response.json()
    def index_fields(group):
        result = {key: group[key] for key in ('id', 'title', 'score', 'first-release-date', 'primary-type', 'secondary-types', 'artist-credit') if key in group}
        if isinstance(result.get('artist-credit'), list):
            result['artist-credit'] = [{**{k: c[k] for k in ('name', 'joinphrase') if k in c}, 'artist': {k: c['artist'][k] for k in ('id', 'name') if k in c.get('artist', {})}} if isinstance(c, dict) else c for c in result['artist-credit']]
        return result
    def save(name, data):
        # Preserve actual identity/date/credit values, omit unused embedded release references.
        if isinstance(data, dict) and 'release-groups' in data:
            data = {**data, 'release-groups': [index_fields(g) for g in data['release-groups']]}
        elif isinstance(data, list):
            data = [index_fields(g) for g in data]
        (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2))
    for name, aid in [('Miles Davis', '561d854a-6a28-4aa7-8c99-323e6ce46c2a'), ('Jeff Beck', '14a4bc78-1c2d-4ca7-8d1b-9b58076a2a17')]:
        if args.artist and args.artist != name:
            continue
        item = {'artist': name, 'artist_id': aid, 'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        prefix = name.replace(' ', '-')
        try:
            started = time.monotonic()
            groups, offset, pages = [], 0, 0
            while True:
                d = get('release-group', query='arid:' + aid + ' AND primarytype:album AND firstreleasedate:[* TO 1979-12-31]', limit=100, offset=offset)
                save(prefix + '-window-' + str(offset) + '.json', d)
                groups.extend(d['release-groups']); offset += len(d['release-groups']); pages += 1
                if offset >= d['count']:
                    break
                if not d['release-groups']:
                    raise ValueError('Incomplete search window')
            item.update(first_window_groups=len(groups), first_window_pages=pages, first_window_seconds=round(time.monotonic() - started, 3))
            groups.sort(key=lambda g: (g.get('first-release-date', ''), g['id']))
            release = get('release', **{'release-group': groups[0]['id'], 'inc': 'labels+media+artist-credits', 'limit': 100, 'offset': 0})
            save(prefix + '-first-editions.json', release)
            item.update(first_group=groups[0]['title'], first_group_date=groups[0].get('first-release-date'), first_release_count=release['release-count'], first_response_seconds=round(time.monotonic() - started, 3))
            started = time.monotonic()
            all_groups, offset, pages = [], 0, 0
            while True:
                d = get('release-group', artist=aid, type='album', inc='artist-credits', limit=100, offset=offset)
                all_groups.extend(d['release-groups']); offset += len(d['release-groups']); pages += 1
                if offset >= d['release-group-count']:
                    break
                if not d['release-groups']:
                    raise ValueError('Incomplete browse index')
            save(prefix + '-browse-index.json', all_groups)
            expected = {g['id'] for g in all_groups if g.get('first-release-date') and g['first-release-date'][:4] <= '1979'}
            found = {g['id'] for g in groups}
            item.update(browse_groups=len(all_groups), browse_pages=pages, browse_index_seconds=round(time.monotonic() - started, 3), missing_from_first_window=sorted(expected-found), unexpected_in_first_window=sorted(found-expected))
            unknown = get('release-group', query='arid:' + aid + ' AND primarytype:album AND NOT firstreleasedate:[* TO *]', limit=100)
            save(prefix + '-unknown.json', unknown)
            item.update(unknown_groups=unknown['count'], unknown_browse_groups=sum(not g.get('first-release-date') for g in all_groups))
            item['ranges'] = []
            covered = [g['id'] for g in groups] + [g['id'] for g in unknown['release-groups']]
            last = max(1980, datetime.datetime.now(datetime.timezone.utc).year // 10 * 10)
            for year in range(1980, last + 1, 10):
                upper = '*' if year == last else str(year + 9) + '-12-31'
                items, offset = [], 0
                while True:
                    d = get('release-group', query='arid:' + aid + ' AND primarytype:album AND firstreleasedate:[' + str(year) + '-01-01 TO ' + upper + ']', limit=100, offset=offset)
                    save(prefix + '-range-' + str(year) + '-' + str(offset) + '.json', d)
                    items.extend(d['release-groups']); offset += len(d['release-groups'])
                    if offset >= d['count']:
                        break
                    if not d['release-groups']:
                        raise ValueError('Incomplete date range')
                expected_ids = {g['id'] for g in all_groups if g.get('first-release-date') and g['first-release-date'][:4] >= str(year) and (upper == '*' or g['first-release-date'][:4] <= upper[:4])}
                actual_ids = {g['id'] for g in items}
                item['ranges'].append({'year': year, 'count': len(items), 'missing': sorted(expected_ids-actual_ids), 'unexpected': sorted(actual_ids-expected_ids)})
                covered.extend(g['id'] for g in items)
            all_ids = {g['id'] for g in all_groups}
            item.update(partition_missing=sorted(all_ids-set(covered)), partition_unexpected=sorted(set(covered)-all_ids), partition_duplicates=len(covered)-len(set(covered)))

        except (requests.RequestException, ValueError, IndexError) as error:
            item['error'] = type(error).__name__ + ': ' + str(error)
        report['artists'].append(item)
        save('live-report.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
