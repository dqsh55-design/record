"""Capture MB album indexes/edition pages for offline classification regressions.

Read-only; no catalog updates. Group IDs are explicit so selection is reviewable.
Requires requests. Example usage is in docs/V0.66-REVIEW.md.
"""
import argparse
import datetime
import json
import time
from pathlib import Path

import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artist-id', required=True)
    parser.add_argument('--group-id', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers['User-Agent'] = 'RECORD/0.66 (https://github.com/dqsh55-design/record)'
    requests_made = []
    previous = 0

    def get(path, **params):
        nonlocal previous
        for attempt in range(3):
            time.sleep(max(0, 1.1 - (time.monotonic() - previous)))
            previous = time.monotonic()
            response = session.get('https://musicbrainz.org/ws/2/' + path,
                                   params={'fmt': 'json', **params}, timeout=30)
            requests_made.append({'url': response.url, 'status': response.status_code})
            if response.status_code not in (429, 502, 503, 504):
                break
        response.raise_for_status()
        return response.json()

    def pages(path, count_key, items_key, **params):
        items, offset = [], 0
        while True:
            data = get(path, limit=100, offset=offset, **params)
            batch = data[items_key]
            if not batch and offset < data[count_key]:
                raise ValueError('Incomplete pagination; refusing to record success')
            items.extend(batch)
            offset += len(batch)
            if offset >= data[count_key]:
                break
        if len({item['id'] for item in items}) != data[count_key]:
            raise ValueError('Duplicate/moving records; retry the capture')
        return items

    groups = pages('release-group', 'release-group-count', 'release-groups',
                   artist=args.artist_id, type='album', inc='artist-credits')
    (args.output / 'artist-index.json').write_text(
        json.dumps(groups, ensure_ascii=False, indent=2), encoding='utf-8')
    by_id = {g['id']: g for g in groups}
    for group_id in args.group_id:
        group = by_id[group_id]
        releases = pages('release', 'release-count', 'releases',
                         **{'release-group': group_id, 'inc': 'labels+media+artist-credits'})
        (args.output / (group_id + '-editions.json')).write_text(
            json.dumps({'group': group, 'releases': releases}, ensure_ascii=False, indent=2), encoding='utf-8')
    (args.output / 'capture.json').write_text(json.dumps({
        'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'artist_id': args.artist_id, 'groups': len(groups), 'group_ids': args.group_id,
        'mode': 'real HTTPS via inherited proxy; TLS verification enabled',
        'complete_artist_release_inventory': False, 'requests': requests_made,
    }, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
