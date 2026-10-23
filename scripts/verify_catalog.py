"""Refresh the catalog consumed by the UI without removing existing records."""
import argparse
import json
import os
import tempfile
from pathlib import Path
from automatic_matching import enrich


def refresh_file(path, music, mb=None, limit=12):
    path = Path(path)
    catalog = json.loads(path.read_text(encoding='utf-8'))
    enrich(catalog, music, mb=mb, max_albums=max(0, limit))
    # A failed write must not truncate the only copy of the existing catalog.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name + '.', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return catalog


class LazyMusic:
    client = None

    def get_album(self, album_id):
        if self.client is None:
            from ytmusicapi import YTMusic
            self.client = YTMusic(location='JP', language='ja')
        return self.client.get_album(album_id)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=12)
    args = parser.parse_args()
    refresh_file('data/ytmusic-albums.json', LazyMusic(), limit=args.limit)
