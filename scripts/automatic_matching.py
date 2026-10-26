"""Conservative, edition-level evidence. Never infer rights holders from prose."""
import datetime
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter


def key(value):
    return ''.join(c for c in unicodedata.normalize('NFKC', str(value or '')).casefold() if c.isalnum())


def usable_label(value):
    return isinstance(value, str) and bool(key(value)) and value.strip().casefold() not in {'[no label]', '[unknown]'}


def ordered_positions(items):
    """Missing/duplicate positions cannot establish a complete ordered disc."""
    positions = [item.get('position') for item in items]
    return bool(items) and all(type(p) is int for p in positions) and sorted(positions) == list(range(1, len(items) + 1))


def release_year(value):
    match = re.fullmatch(r'([1-9][0-9]{3})(?:-[0-9]{2}(?:-[0-9]{2})?)?', str(value or ''))
    return match.group(1) if match else None


def youtube_evidence(album_id, detail):
    tracks = [{'position': i + 1, 'title': t.get('title'), 'video_id': t.get('videoId')}
              for i, t in enumerate(detail.get('tracks') or [])]
    # Description/copyright is retained verbatim, never parsed into a label.
    return {'source': 'https://music.youtube.com/browse/' + album_id,
            'title': detail.get('title'), 'year': release_year(detail.get('year')),
            'artists': [a.get('name') for a in detail.get('artists') or []],
            'labels': [detail['label']] if usable_label(detail.get('label')) else [],
            'publisher': detail.get('publisher') if isinstance(detail.get('publisher'), str) else None,
            'description': detail.get('description'), 'track_count': detail.get('trackCount'),
            'tracks': tracks,
            'complete': bool(tracks) and type(detail.get('trackCount')) is int and detail.get('trackCount') == len(tracks)
                        and all(key(t['title']) for t in tracks)}


def compare(yt, release, *, full_release=False):
    media = sorted(release.get('media') or [], key=lambda m: m.get('position', 0))
    tracks = [t for m in media for t in sorted(m.get('tracks') or [], key=lambda t: t.get('position', 0))]
    titles = [key(t.get('title')) for t in tracks]
    ytitles = [key(t.get('title')) for t in yt.get('tracks', [])]
    # The full /release/{id}?inc=recordings endpoint returns all media, but
    # unlike release search, normally omits medium-count. Do not require a
    # search-only field on that endpoint; still reject any conflicting count.
    media_complete = (release.get('medium-count') == len(media)
                      if type(release.get('medium-count')) is int
                      else full_release and 'medium-count' not in release)
    complete = ordered_positions(media) and all(
        type(m.get('track-count')) is int and m.get('track-count') == len(m.get('tracks') or [])
        and ordered_positions(m.get('tracks') or []) for m in media
    ) and media_complete and all(titles)
    labels = [li['label']['name'] for li in release.get('label-info', []) if usable_label((li.get('label') or {}).get('name'))]
    credits = [a for a in release.get('artist-credit', []) if isinstance(a, dict)]
    artists = [a.get('name') or (a.get('artist') or {}).get('name') for a in credits]
    yt_artists = yt.get('artists') or []
    # A nameless collaborator is missing evidence, not permission to ignore them.
    artists_complete = bool(artists) and all(key(a) for a in artists) and bool(yt_artists) and all(key(a) for a in yt_artists)
    checks = {
        'official': 'match' if release.get('status') == 'Official' else ('different' if release.get('status') else 'unknown'),
        'title': ('match' if key(yt.get('title')) == key(release.get('title')) else 'different') if key(yt.get('title')) and key(release.get('title')) else 'unknown',
        'artist': ('match' if {key(a) for a in yt_artists} == {key(a) for a in artists} else 'different') if artists_complete else 'unknown',
        'label': ('match' if {key(x) for x in yt['labels']} == {key(x) for x in labels}
                  else 'unknown' if {key(x) for x in yt['labels']} & {key(x) for x in labels}
                  else 'different') if yt.get('labels') and labels and all(usable_label((li.get('label') or {}).get('name')) for li in release.get('label-info', [])) else 'unknown',
        'year': ('match' if release_year(yt.get('year')) == release_year(release.get('date')) else 'different') if release_year(yt.get('year')) and release_year(release.get('date')) else 'unknown',
        'count': 'unknown', 'titles': 'unknown', 'order': 'unknown'}
    if yt.get('complete') and complete:
        checks.update(count='match' if len(titles) == len(ytitles) else 'different',
                      titles='match' if Counter(titles) == Counter(ytitles) else 'different',
                      order='match' if titles == ytitles else 'different')
    status = 'supported' if all(v == 'match' for v in checks.values()) else ('different' if 'different' in checks.values() else 'insufficient')
    return {'status': status, 'checks': checks, 'release_id': release.get('id'),
            'source': 'https://musicbrainz.org/release/' + release.get('id', ''),
            'title': release.get('title'), 'date': release.get('date'), 'country': release.get('country'),
            'artists': artists, 'labels': labels, 'catalog_numbers': [li['catalog-number'] for li in release.get('label-info', []) if li.get('catalog-number')], 'track_count': len(tracks) if complete else None,
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
    result = {'version': 2, 'album_id': album['id'], 'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'status': 'insufficient', 'candidates': [], 'limitations': []}
    try:
        if not re.fullmatch(r'MPREb_[A-Za-z0-9_-]+', album['id']):
            raise ValueError('Not an album browse ID')
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
        artists = [a for a in yt.get('artists') or [] if key(a)]
        if artists:
            query += ' AND artist:"' + quoted(artists[0]) + '"'
        search = mb.get('release/', query=query, limit=25)
        found = search.get('releases', [])
        truncated = search.get('count', 0) > len(found)
        if truncated:
            result['limitations'].append('発売盤候補が多いため、先頭25件のみ照合しました。')
        for candidate in found:
            release = mb.get('release/' + candidate['id'], inc='labels+recordings+artist-credits')
            result['candidates'].append(compare(yt, release, full_release=True))
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

