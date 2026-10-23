"""Refresh evidence without rediscovering or removing existing album links."""
import json
from pathlib import Path
from ytmusicapi import YTMusic
from automatic_matching import enrich

if __name__ == '__main__':
    path = Path('data/ytmusic-albums.json')
    catalog = json.loads(path.read_text(encoding='utf-8'))
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=12)
    args = parser.parse_args()
    class LazyMusic:
        client = None
        def get_album(self, album_id):
            if self.client is None:
                self.client = YTMusic(location='JP', language='ja')
            return self.client.get_album(album_id)
    enrich(catalog, LazyMusic(), max_albums=max(0, args.limit))
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
