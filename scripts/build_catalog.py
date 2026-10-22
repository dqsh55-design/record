import json, pathlib
from ytmusicapi import YTMusic

music = YTMusic(location="JP", language="ja")
queries = {
    "Miles Davis": [
        "Miles Davis", "Miles Davis albums", "Miles Davis discography",
        "Miles Davis Kind of Blue", "Miles Davis Bitches Brew",
        "Miles Davis Sketches of Spain", "Miles Davis In a Silent Way",
        "Miles Davis Milestones", "Miles Davis Porgy and Bess",
        "Miles Davis Birth of the Cool", "Miles Davis Round About Midnight",
        "Miles Davis Someday My Prince Will Come", "Miles Davis Nefertiti",
        "Miles Davis E.S.P.", "Miles Davis Sorcerer", "Miles Davis Filles de Kilimanjaro",
        "Miles Davis Jack Johnson", "Miles Davis On the Corner",
        "Miles Davis Get Up with It", "Miles Davis Agharta",
        "Miles Davis Pangaea", "Miles Davis Tutu", "Miles Davis Amandla",
        "Miles Davis Doo Bop", "Miles Davis live", "Miles Davis greatest hits",
        "Miles Davis best of", "Miles Davis complete sessions",
        "Miles Davis 1950s", "Miles Davis 1960s", "Miles Davis 1970s",
        "Miles Davis 1980s", "Miles Davis 1990s"
    ],
    "Duke Ellington": ["Duke Ellington", "Duke Ellington albums", "Duke Ellington live", "Duke Ellington best of", "Duke Ellington Ellington at Newport", "Duke Ellington Money Jungle", "Duke Ellington Far East Suite", "Duke Ellington Such Sweet Thunder", "Duke Ellington Masterpieces by Ellington"],
    "Stan Getz": ["Stan Getz", "Stan Getz albums", "Stan Getz Getz Gilberto", "Stan Getz Jazz Samba", "Stan Getz Focus", "Stan Getz live", "Stan Getz best of"],
    "John Coltrane": ["John Coltrane", "John Coltrane albums", "John Coltrane A Love Supreme", "John Coltrane Blue Train", "John Coltrane Giant Steps", "John Coltrane My Favorite Things", "John Coltrane Ballads", "John Coltrane live", "John Coltrane best of"],
    "Chick Corea": ["Chick Corea", "Chick Corea albums", "Chick Corea Return to Forever", "Chick Corea Light as a Feather", "Chick Corea Now He Sings Now He Sobs", "Chick Corea live", "Chick Corea best of"],
    "Jeff Beck": ["Jeff Beck", "Jeff Beck albums", "Jeff Beck Blow by Blow", "Jeff Beck Wired", "Jeff Beck There and Back", "Jeff Beck Guitar Shop", "Jeff Beck live", "Jeff Beck best of"],
    "The Beatles": ["The Beatles", "The Beatles albums", "The Beatles Abbey Road", "The Beatles Revolver", "The Beatles Rubber Soul", "The Beatles Sgt Pepper", "The Beatles White Album", "The Beatles Let It Be", "The Beatles live", "The Beatles greatest hits"]
}
catalog = {}
for artist, terms in queries.items():
    found = {}
    errors = []
    artist_key = artist.casefold().replace("the ", "").strip()
    for term in terms:
        try:
            for item in music.search(term, limit=50):
                if item.get("resultType") != "album": continue
                album_id = item.get("browseId", "")
                if not album_id.startswith("MPREb_"): continue
                artists = [a.get("name", "") for a in item.get("artists", [])]
                normalized_names = [name.casefold().replace("the ", "").strip() for name in artists]
                if not any(artist_key in name or name in artist_key for name in normalized_names if name): continue
                found[album_id] = {
                    "id": album_id, "title": item.get("title", ""),
                    "year": item.get("year"), "artists": artists,
                    "thumbnail": (item.get("thumbnails") or [{}])[-1].get("url", ""),
                    "url": "https://music.youtube.com/browse/" + album_id
                }
        except Exception as error:
            errors.append((term, str(error)))
            print("Search error:", term, str(error))
    # Artist pages expose additional albums that ordinary keyword searches can miss.
    try:
        artist_results = music.search(artist, filter="artists", limit=20)
        for result in artist_results:
            namestr = result.get("artist", result.get("title", ""))
            if artist_key not in str(namestr).casefold().replace("the ", "").strip():
                continue
            channel_id = result.get("browseId")
            if not channel_id: continue
            details = music.get_artist(channel_id)
            for key in ("albums", "singles", "compilations", "live"):
                section = details.get(key) or {}
                entries = section.get("results", [])
                if section.get("browseId") and section.get("params"):
                    try:
                        entries = music.get_artist_albums(section["browseId"], section["params"], limit=300)
                    except Exception as error:
                        print("Artist section error:", artist, key, error)
                for item in entries:
                    aid = item.get("browseId", "")
                    if not aid.startswith("MPREb_"): continue
                    if aid in found: continue
                    found[aid] = {
                        "id": aid, "title": item.get("title", ""),
                        "year": item.get("year"), "artists": [artist],
                        "thumbnail": (item.get("thumbnails") or [{}])[-1].get("url", ""),
                        "url": "https://music.youtube.com/browse/" + aid
                    }
            break
    except Exception as error:
        print("Artist browsing error:", artist, error)
    catalog[artist] = sorted(found.values(), key=lambda x: (str(x["year"] or "9999"), x["title"]))
    print(artist, len(catalog[artist]))
if not catalog["Miles Davis"]: raise SystemExit("No albums found; do not publish empty catalog")
pathlib.Path("data").mkdir(exist_ok=True)
pathlib.Path("data/ytmusic-albums.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
