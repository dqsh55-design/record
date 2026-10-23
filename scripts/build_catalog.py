import json, pathlib, re, time, urllib.parse, urllib.request
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
    "Jimi Hendrix": [
        "Jimi Hendrix", "Jimi Hendrix albums", "Jimi Hendrix Are You Experienced",
        "Jimi Hendrix Axis Bold as Love", "Jimi Hendrix Electric Ladyland",
        "Jimi Hendrix Band of Gypsys", "Jimi Hendrix live",
        "Jimi Hendrix posthumous", "Jimi Hendrix compilation",
        "The Jimi Hendrix Experience"
    ],
    "Janis Joplin": [
        "Janis Joplin", "Janis Joplin albums", "Janis Joplin Pearl",
        "Janis Joplin I Got Dem Ol Kozmic Blues Again Mama",
        "Janis Joplin Cheap Thrills", "Janis Joplin Big Brother",
        "Janis Joplin live", "Janis Joplin greatest hits",
        "Janis Joplin posthumous"
    ],
    "The Beatles": ["The Beatles", "The Beatles albums", "The Beatles Abbey Road", "The Beatles Revolver", "The Beatles Rubber Soul", "The Beatles Sgt Pepper", "The Beatles White Album", "The Beatles Let It Be", "The Beatles live", "The Beatles greatest hits"]
}
catalog_path = pathlib.Path("data/ytmusic-albums.json")
try:
    previous = json.loads(catalog_path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    previous = {}
# Known artist ensembles are not mistaken for unrelated performers.
artist_aliases = {
    "Miles Davis": {"miles davis quintet", "miles davis sextet"},
    "Duke Ellington": {"duke ellington and his orchestra", "duke ellington & his orchestra", "duke ellington & his famous orchestra", "duke ellington and his famous orchestra"},
    "Stan Getz": {"stan getz quintet", "stan getz quartet"},
    "John Coltrane": {"the john coltrane quartet", "john coltrane quartet"},
    "Jeff Beck": {"jeff beck group"},
    "Jimi Hendrix": {"the jimi hendrix experience", "band of gypsys"},
    "Janis Joplin": {"big brother & the holding company", "big brother and the holding company"},
}
def title_key(value):
    # Normalize punctuation and spacing without fragile regex escaping.
    return " ".join((value or "").casefold().split())

def musicbrainz_json(path, params):
    url = "https://musicbrainz.org/ws/2/" + path + "?" + urllib.parse.urlencode({**params, "fmt": "json"})
    req = urllib.request.Request(url, headers={
        "User-Agent": "RECORD/0.22 (noncommercial music album guide)",
        "Accept": "application/json"
    })
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)

# Initial curated release-year set checked against the Miles Davis
# discography on MusicBrainz. Extend only after reviewing each album.
MILES_ORIGINAL_YEARS = {
    "Kind of Blue": "1959",
    "Bitches Brew": "1970",
    "Tutu": "1986",
    "Sketches of Spain": "1960",
    "Milestones": "1958",
    "Porgy and Bess": "1958",
    "Miles Ahead": "1957",
    "Nefertiti": "1968",
    "In a Silent Way": "1969",
    "Filles de Kilimanjaro": "1969",
    "Sorcerer": "1967",
    "E.S.P.": "1965",
    "On the Corner": "1972",
    "Get Up With It": "1974",
    "Amandla": "1989",
    "Decoy": "1984",
    "Star People": "1983",
    "Quiet Nights": "1963",
    "Seven Steps to Heaven": "1963",
    "The Man With the Horn": "1981",
    "Big Fun": "1974",
    "Water Babies": "1976",
    "Birth of the Cool": "1957",
    "Doo-Bop": "1992",
}
def original_years_for_miles():
    return {title_key(title): year for title, year in MILES_ORIGINAL_YEARS.items()}

catalog = {}
for artist, terms in queries.items():
    found = {}
    errors = []
    artist_key = artist.casefold().removeprefix("the ").strip()
    for term in terms:
        try:
            for item in music.search(term, limit=50):
                if item.get("resultType") != "album": continue
                album_id = item.get("browseId", "")
                if not album_id.startswith("MPREb_"): continue
                artists = [a.get("name", "") for a in item.get("artists", [])]
                normalized_names = [name.casefold().removeprefix("the ").strip() for name in artists]
                allowed = {artist_key} | artist_aliases.get(artist, set())
                if not any(name in allowed for name in normalized_names if name): continue
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
        if artist == "Jimi Hendrix":
            artist_results += music.search("The Jimi Hendrix Experience", filter="artists", limit=20)
        for result in artist_results:
            namestr = result.get("artist", result.get("title", ""))
            allowed = {artist_key} | artist_aliases.get(artist, set())
            if str(namestr).casefold().removeprefix("the ").strip() not in allowed:
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
    # Keep previously discovered albums when YouTube search is inconsistent.
    for item in previous.get(artist, []):
        if item.get("id", "").startswith("MPREb_"):
            found.setdefault(item["id"], item)
    # Verify artist identity using the album detail endpoint. Keep uncertain
    # results in the catalog, but mark them as unverified for the UI.
    checked = 0
    for album in found.values():
        album["artist_check"] = "unverified"
        try:
            detail = music.get_album(album["id"])
            detail_artists = [a.get("name", "") for a in detail.get("artists", [])]
            if not detail_artists:
                continue
            detail_keys = [name.casefold().removeprefix("the ").strip() for name in detail_artists]
            allowed = {artist_key} | artist_aliases.get(artist, set())
            if any(key in allowed for key in detail_keys):
                album["artist_check"] = "matched"
                album["artists"] = detail_artists
                album["year"] = detail.get("year") or album.get("year")
                album["track_count"] = len(detail.get("tracks") or [])
            else:
                album["artist_check"] = "mismatch"
                album["detail_artists"] = detail_artists
            checked += 1
        except Exception as error:
            print("Album detail error:", artist, album["id"], str(error))
    print("Album details checked:", artist, checked)
    mb_years = original_years_for_miles() if artist == "Miles Davis" else {}
    for album in found.values():
        album.pop("original_year", None)
        album.pop("year_source", None)
        if album.get("artist_check") != "matched":
            continue
        year = mb_years.get(title_key(album["title"]))
        if year:
            album["original_year"] = year
            album["year_source"] = "MusicBrainz discography (curated)"
    catalog[artist] = sorted(found.values(), key=lambda x: (str(x.get("original_year") or "9999"), x["title"]))
    print(artist, len(catalog[artist]))
if not catalog["Miles Davis"]: raise SystemExit("No albums found; do not publish empty catalog")
pathlib.Path("data").mkdir(exist_ok=True)
pathlib.Path("data/ytmusic-albums.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
