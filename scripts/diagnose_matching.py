"""Read-only real-service diagnostics; never writes the application catalog.

Uses inherited proxy/CA settings. No cookies, alternate hosts or direct routes.
"""
import argparse
import datetime
import importlib.metadata
import json
from pathlib import Path
import urllib.error
import urllib.request

from automatic_matching import MusicBrainz, compare, youtube_evidence
from verify_catalog import LazyMusic


TARGETS = [
    ('Jeff Beck', 'Blow by Blow', 'MPREb_jT1i6yytIdA'),
    ('Jeff Beck', 'Best of Beck', 'MPREb_ad4e4La82DZ'),
    ('Miles Davis', 'Kind of Blue', 'MPREb_iNbKdKjDqyr'),
]


def failure(error):
    # Do not serialize exception messages: proxy URLs can contain credentials.
    chain, pending, seen = [], [error], set()
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        chain.append(str(item))
        for child in (item.__cause__, item.__context__, getattr(item, 'reason', None)):
            if isinstance(child, BaseException):
                pending.append(child)
    text = ' '.join(chain).lower()
    category = ('proxy_connect_403' if ('tunnel connection failed: 403' in text or
                                      'connect tunnel failed' in text and '403' in text)
                else 'proxy_connection' if 'proxy' in text
                else 'http_error' if isinstance(error, urllib.error.HTTPError)
                else 'connection_or_response_error')
    return {'category': category, 'exception': type(error).__name__,
            'http_status': error.code if isinstance(error, urllib.error.HTTPError) else None}


def probe(url):
    try:
        request = urllib.request.Request(url, method='HEAD')
        with urllib.request.urlopen(request, timeout=20) as response:
            return {'url': url, 'http_status': response.status}
    except Exception as error:
        return {'url': url, 'error': failure(error)}


def diagnose(music, mb, candidate_limit=3):
    report = {'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'purpose': 'diagnostic_only_not_catalog_evidence', 'targets': []}
    for artist, title, album_id in TARGETS:
        item = {'artist': artist, 'title': title, 'album_id': album_id,
                'status': 'insufficient', 'candidates': []}
        report['targets'].append(item)
        yt = None
        try:
            yt = youtube_evidence(album_id, music.get_album(album_id))
            item['youtube'] = yt
        except Exception as error:
            item['youtube_error'] = failure(error)
        # Fetch MB independently even when YouTube Music is unavailable.
        try:
            search = mb.get('release/', query=f'release:"{title}" AND artist:"{artist}" AND status:official', limit=candidate_limit)
            item['musicbrainz_total'] = search.get('count')
            item['candidate_search_only'] = True
            for entry in search.get('releases', []):
                release = mb.get('release/' + entry['id'], inc='labels+recordings+artist-credits')
                # An empty YouTube side produces unknown checks, not a match.
                item['candidates'].append(compare(yt or {}, release, full_release=True))
            item['comparison_available'] = yt is not None
            # This bounded diagnostic deliberately makes no global verdict.
        except Exception as error:
            item['musicbrainz_error'] = failure(error)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.output.resolve().is_relative_to(root / 'data'):
        parser.error('Diagnostic output must be outside data/; use work/ or an artifact directory.')
    report = diagnose(LazyMusic(), MusicBrainz())
    report['transport'] = [probe('https://music.youtube.com/'), probe('https://musicbrainz.org/')]
    report['ytmusicapi_version'] = importlib.metadata.version('ytmusicapi')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Diagnostic saved; no catalog modified:', args.output)


if __name__ == '__main__':
    main()
