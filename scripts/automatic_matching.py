"""Conservative, edition-level evidence. Never infer rights holders from prose."""
import datetime
import json
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter


def key(value):
    return ''.join(c for c in unicodedata.normalize('NFKC', str(value or '')).casefold() if c.isalnum())


def usable_label(value):
    return isinstance(value, str) and bool(key(value)) and value.strip().casefold() not in {'[no label]', '[unknown]'}


def youtube_evidence(album_id, detail):
    tracks = [{'position': i + 1, 'title': t.get('title'), 'video_id': t.get('videoId')}
              for i, t in enumerate(detail.get('tracks') or [])]
    # Description/copyright is retained verbatim, never parsed into a label.
    return {'source': 'https://music.youtube.com/browse/' + album_id,
            'title': detail.get('title'),
            'artists': [a.get('name') for a in detail.get('artists', []) if a.get('name')],
            'labels': [detail['label']] if usable_label(detail.get('label')) else [],
            'publisher': detail.get('publisher') if isinstance(detail.get('publisher'), str) else None,
            'description': detail.get('description'), 'track_count': detail.get('trackCount'),
            'tracks': tracks,
            'complete': bool(tracks) and detail.get('trackCount') == len(tracks)
                        and all(t['title'] for t in tracks)}


def compare(yt, release):
    media = sorted(release.get('media') or [], key=lambda m: m.get('position', 0))
    tracks = [t for m in media for t in sorted(m.get('tracks') or [], key=lambda t: t.get('position', 0))]
    titles = [key(t.get('title')) for t in tracks]
    ytitles = [key(t.get('title')) for t in yt.get('tracks', [])]
    complete = bool(media) and all(m.get('track-count') == len(m.get('tracks') or []) for m in media) and release.get('medium-count') == len(media) and all(titles)
    labels = [li['label']['name'] for li in release.get('label-info', []) if usable_label((li.get('label') or {}).get('name'))]
    artists = [a['artist']['name'] for a in release.get('artist-credit', []) if isinstance(a, dict) and a.get('artist', {}).get('name')]
    checks = {
        'official': 'match' if release.get('status') == 'Official' else ('different' if release.get('status') else 'unknown'),
        'title': 'match' if key(yt.get('title')) and key(yt.get('title')) == key(release.get('title')) else 'different',
        'artist': ('match' if {key(a) for a in yt.get('artists', [])} == {key(a) for a in artists} else 'different') if artists and yt.get('artists') else 'unknown',
        'label': ('match' if {key(x) for x in yt['labels']} & {key(x) for x in labels} else 'different') if yt.get('labels') and labels else 'unknown',
        'count': 'unknown', 'titles': 'unknown', 'order': 'unknown'}
    if yt.get('complete') and complete:
        checks.update(count='match' if len(titles) == len(ytitles) else 'different',
                      titles='match' if Counter(titles) == Counter(ytitles) else 'different',
                      order='match' if titles == ytitles else 'different')
    status = 'supported' if all(v == 'match' for v in checks.values()) else ('different' if 'different' in checks.values() else 'insufficient')
    return {'status': status, 'checks': checks, 'release_id': release.get('id'),
            'source': 'https://musicbrainz.org/release/' + release.get('id', ''),
            'title': release.get('title'), 'date': release.get('date'), 'country': release.get('country'),
            'labels': labels, 'catalog_numbers': [li['catalog-number'] for li in release.get('label-info', []) if li.get('catalog-number')], 'track_count': len(tracks) if complete else None,
            'tracks': [{'position': i + 1, 'title': t.get('title')} for i, t in enumerate(tracks)]}


class MusicBrainz:
    def __init__(self):
        self.last = 0
        self.cache = {}
        self.deadline = time.monotonic() + 600

    def get(self, path, **params):
        if time.monotonic() >= self.deadline:
            raise TimeoutError('Evidence refresh time budget exhausted')
        url = 'https://musicbrainz.org/ws/2/' + path + '?' + urllib.parse.urlencode({**params, 'fmt': 'json'})
        if url in self.cache:
            return self.cache[url]
        time.sleep(max(0, 1.1 - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        request = urllib.request.Request(url, headers={'User-Agent': 'RECORD/0.59 (https://github.com/dqsh55-design/record)', 'Accept': 'application/json'})
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.load(response)
        self.cache[url] = data
        return data


def verify_album(album, music, mb):
    result = {'version': 1, 'album_id': album['id'], 'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'status': 'insufficient', 'candidates': [], 'limitations': []}
    try:
        yt = youtube_evidence(album['id'], music.get_album(album['id']))
        result['youtube'] = yt
        if not yt['labels']:
            result['limitations'].append('YouTube Musicのレーベル情報を取得できませんでした。')
        if not yt['complete']:
            result['limitations'].append('YouTube Musicの全収録曲を確認できませんでした。')
        # Title is a candidate search only. Every decision uses release details.
        def quoted(s):
            return str(s).replace('\\', '\\\\').replace('"', '\\"')
        query = 'release:"' + quoted(yt.get('title') or album['title']) + '" AND status:official'
        artists = yt.get('artists') or []
        if artists:
            query += ' AND artist:"' + quoted(artists[0]) + '"'
        search = mb.get('release/', query=query, limit=25)
        found = search.get('releases', [])
        truncated = search.get('count', 0) > len(found)
        if truncated:
            result['limitations'].append('発売盤候補が多いため、先頭25件のみ照合しました。')
        for candidate in found:
            release = mb.get('release/' + candidate['id'], inc='labels+recordings+artist-credits')
            result['candidates'].append(compare(yt, release))
        statuses = [c['status'] for c in result['candidates']]
        if 'supported' in statuses:
            result['status'] = 'supported'
        elif statuses and all(s == 'different' for s in statuses) and not truncated:
            result['status'] = 'different'
        if not found:
            result['limitations'].append('照合できる公式発売盤候補が見つかりませんでした。')
    except Exception as error:
        result['status'] = 'insufficient'
        result['limitations'].append('外部情報の取得に失敗しました（' + type(error).__name__ + '）。')
    return result


def enrich(catalog, music, mb=None, max_albums=12):
    mb = mb or MusicBrainz()
    albums = [a for entries in catalog.values() for a in entries]
    albums.sort(key=lambda a: a.get('automatic_verification', {}).get('checked_at', ''))
    started = time.monotonic()
    for album in albums[:max_albums]:
        if time.monotonic() - started >= 600:
            break
        album['automatic_verification'] = verify_album(album, music, mb)
    return catalog
