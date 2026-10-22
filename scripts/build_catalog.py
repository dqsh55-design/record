import json, pathlib
from ytmusicapi import YTMusic

music = YTMusic(location="JP", language="ja")
queries = {"Miles Davis": ["Miles Davis", "Miles Davis Kind of Blue", "Miles Davis Bitches Brew", "Miles Davis Sketches of Spain"]}
catalog = {}
for artist, terms in queries.items():
    found = {}
    for term in terms:
        try:
            for item in music.search(term, limit=50):
                if item.get("resultType") != "album": continue
                album_id = item.get("browseId", "")
                if not album_id.startswith("MPREb_"): continue
                artists = [a.get("name", "") for a in item.get("artists", [])]
                if not any(artist.casefold() in name.casefold() for name in artists): continue
                found[album_id] = {
                    "id": album_id, "title": item.get("title", ""),
                    "year": item.get("year"), "artists": artists,
                    "thumbnail": (item.get("thumbnails") or [{}])[-1].get("url", ""),
                    "url": "https://music.youtube.com/browse/" + album_id
                }
        except Exception as error:
            print("Search error:", term, str(error))
    catalog[artist] = sorted(found.values(), key=lambda x: (str(x["year"] or "9999"), x["title"]))
    print(artist, len(catalog[artist]))
if not catalog["Miles Davis"]: raise SystemExit("No albums found; do not publish empty catalog")
pathlib.Path("data").mkdir(exist_ok=True)
pathlib.Path("data/ytmusic-albums.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
