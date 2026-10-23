import json, pathlib, re, time, urllib.parse, urllib.request, urllib.error
from ytmusicapi import YTMusic
from release_matching import release_evidence, supported_group

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

# Reusable bridge: MusicBrainz discography -> YouTube Music album links.
# Start with one artist identity; the algorithm does not hardcode album titles.
def bridge_discography(artist_name, mbid, limit=25):
    results = []
    diagnostics = {"artist": artist_name, "musicbrainz_id": mbid, "albums_checked": 0, "no_candidates": [], "title_mismatch": [], "artist_mismatch": [], "detail_mismatch": [], "matched": []}
    try:
        endpoint = ("https://musicbrainz.org/ws/2/release-group?artist=" +
                    urllib.parse.quote(mbid) + "&type=album&limit=100&fmt=json")
        req = urllib.request.Request(endpoint, headers={
            "User-Agent": "RECORD/0.26 (music discovery prototype)",
            "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=25) as response:
            groups = json.load(response).get("release-groups", [])
    except Exception as error:
        print("MusicBrainz bridge error:", artist_name, error)
        diagnostics["musicbrainz_error"] = str(error)
        return results, diagnostics
    # Studio albums first; no individual title is built into the program.
    groups.sort(key=lambda g: (bool(g.get("secondary-types")),
                               g.get("first-release-date") or "9999"))
    allowed = {artist_name.casefold().removeprefix("the ").strip()}
    allowed |= artist_aliases.get("Jimi Hendrix", set()) if artist_name == "The Jimi Hendrix Experience" else set()
    for group in [g for g in groups if supported_group(g)][:limit]:
        diagnostics["albums_checked"] += 1
        title = group.get("title", "")
        if not title: continue
        try:
            # Some YouTube Music regions/queries return no results with the
            # albums filter even when the general search finds album cards.
            candidates = music.search(artist_name + " " + title, filter="albums", limit=20)
            if not candidates:
                fallback = music.search(artist_name + " " + title, limit=50)
                candidates = [x for x in fallback if x.get("resultType") == "album"]
                if candidates:
                    diagnostics.setdefault("fallback_found", []).append({"title": title, "count": len(candidates)})
            if not candidates:
                diagnostics["no_candidates"].append(title)
            matched = False
            for item in candidates:
                aid = item.get("browseId", "")
                if not aid.startswith("MPREb_"): continue
                if title_key(item.get("title", "")) != title_key(title):
                    diagnostics["title_mismatch"].append({"wanted": title, "found": item.get("title", "")})
                    continue
                names = [a.get("name", "") for a in item.get("artists", [])]
                if not names and item.get("artist"): names = [item["artist"]]
                if not any(n.casefold().removeprefix("the ").strip() in allowed for n in names):
                    diagnostics["artist_mismatch"].append({"wanted": title, "artists": names})
                    continue
                detail = music.get_album(aid)
                actual = [a.get("name", "") for a in detail.get("artists", [])]
                if not any(n.casefold().removeprefix("the ").strip() in allowed for n in actual):
                    diagnostics["detail_mismatch"].append({"wanted": title, "artists": actual})
                    continue
                # Inspect release-level publisher and recording metadata; never
                # promote a title/artist association into proof of an official edition.
                time.sleep(1.2)
                try:
                    release_data = musicbrainz_json("release", {
                        "release-group": group["id"], "inc": "labels+recordings+artist-credits", "limit": 100})
                    evidence = release_evidence(group, detail, release_data.get("releases", []),
                                               [artist_name, *artist_aliases.get(artist_name, set())])
                    evidence["release_count"] = release_data.get("release-count", len(release_data.get("releases", [])))
                    evidence["truncated"] = evidence["release_count"] > len(release_data.get("releases", []))
                except Exception as error:
                    evidence = release_evidence(group, detail, [], [artist_name])
                    evidence["retrieval_error"] = str(error)
                    diagnostics.setdefault("release_errors", []).append({"title": title, "error": str(error)})
                results.append({
                    "id": aid, "title": item.get("title", title),
                    "year": detail.get("year"), "original_year": (group.get("first-release-date") or "")[:4],
                    "year_source": "MusicBrainz release group",
                    "artists": actual, "artist_check": "matched",
                    "thumbnail": (item.get("thumbnails") or detail.get("thumbnails") or [{}])[-1].get("url", ""),
                    "track_count": len(detail.get("tracks") or []),
                    "url": "https://music.youtube.com/browse/" + aid,
                    "mb_release_group": group.get("id"),
                    "match_method": "release_metadata" if evidence["status"] == "corroborated" else "artist_and_title_candidate",
                    "match_evidence": evidence
                })
                diagnostics["matched"].append(title)
                matched = True
                break
            if not matched: print("Bridge unmatched:", artist_name, title, "candidates:", len(candidates))
        except Exception as error:
            print("Bridge search error:", artist_name, title, error)
    return results, diagnostics

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
    # A named band's releases can appear under its own artist identity.
    # Query both exact album names and band + album combinations.
    if artist == "Jimi Hendrix":
        for title in ("Are You Experienced", "Axis: Bold as Love", "Electric Ladyland"):
            for term in (title + " The Jimi Hendrix Experience", title + " Jimi Hendrix"):
                try:
                    for item in music.search(term, filter="albums", limit=50):
                        aid = item.get("browseId", "")
                        if not aid.startswith("MPREb_"): continue
                        if title_key(item.get("title", "")) != title_key(title): continue
                        names = [a.get("name", "") for a in item.get("artists", [])]
                        keys = [name.casefold().removeprefix("the ").strip() for name in names]
                        allowed = {artist_key} | artist_aliases.get(artist, set())
                        if not any(key in allowed for key in keys): continue
                        found.setdefault(aid, {
                            "id": aid, "title": item.get("title", ""),
                            "year": item.get("year"), "artists": names,
                            "thumbnail": (item.get("thumbnails") or [{}])[-1].get("url", ""),
                            "url": "https://music.youtube.com/browse/" + aid
                        })
                except Exception as error:
                    print("Targeted album search error:", title, str(error))
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
    prior_by_id = {a.get("id"): a for a in previous.get(artist, []) if a.get("id")}
    for album in found.values():
        # Preserve previously verified metadata across catalog rebuilds.
        # Never copy metadata across albums merely because their titles match.
        prior = prior_by_id.get(album.get("id"), {})
        for field in ("match_evidence", "match_method"):
            if field not in album and field in prior:
                album[field] = prior[field]
        if album.get("artist_check") != "matched":
            album.pop("original_year", None)
            album.pop("year_source", None)
            continue
        year = mb_years.get(title_key(album["title"]))
        if year:
            album["original_year"] = year
            album["year_source"] = "MusicBrainz discography (curated)"
        elif prior.get("original_year") and re.fullmatch(r"[0-9]{4}", str(prior["original_year"])):
            album["original_year"] = prior["original_year"]
            album["year_source"] = prior.get("year_source") or "Previously verified catalog"
        else:
            album.pop("original_year", None)
            album.pop("year_source", None)
        if not album.get("mb_release_group") and prior.get("mb_release_group"):
            album["mb_release_group"] = prior["mb_release_group"]
    catalog[artist] = sorted(found.values(), key=lambda x: (str(x.get("original_year") or "9999"), x["title"]))
    print(artist, len(catalog[artist]))
# Reusable bridge for artist identities, not a list of hardcoded albums.
# Keep prior verified matches when an external search intermittently fails.
bridge_targets = [
    ("The Jimi Hendrix Experience", 25),
    ("Janis Joplin", 20),
    ("Jeff Beck", 15),
]
bridge_reports = {}
for target_name, target_limit in bridge_targets:
    try:
        q = urllib.parse.quote('artist:"' + target_name + '"')
        req = urllib.request.Request(
            "https://musicbrainz.org/ws/2/artist/?query=" + q + "&fmt=json&limit=10",
            headers={"User-Agent": "RECORD/0.27 (music discovery prototype)"})
        artists_mb = []
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=25) as response:
                    artists_mb = json.load(response).get("artists", [])
                break
            except urllib.error.HTTPError as error:
                if error.code not in (429, 502, 503, 504) or attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
        time.sleep(1.2)  # Respect MusicBrainz public API rate limits.
        match = next((a for a in artists_mb if a.get("name", "").casefold() == target_name.casefold()), None)
        if not match:
            bridge_reports[target_name] = {"error": "MusicBrainz artist identity not found"}
            continue
        bridged, diagnostic = bridge_discography(target_name, match["id"], limit=target_limit)
        bridge_reports[target_name] = diagnostic
        existing = catalog.get(target_name, [])
        by_id = {a["id"]: a for a in existing if a.get("id")}
        for album in previous.get(target_name, []):
            if album.get("id"): by_id.setdefault(album["id"], album)
        for album in bridged:
            by_id[album["id"]] = album
        catalog[target_name] = sorted(by_id.values(), key=lambda x: (str(x.get("original_year") or "9999"), x.get("title", "")))
        print("Bridge", target_name, "new:", len(bridged), "total:", len(catalog[target_name]))
    except Exception as error:
        bridge_reports[target_name] = {"error": str(error)}
        print("Bridge error:", target_name, error)
pathlib.Path("data").mkdir(exist_ok=True)
pathlib.Path("data/bridge-diagnostics.json").write_text(
    json.dumps(bridge_reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
if not catalog["Miles Davis"]: raise SystemExit("No albums found; do not publish empty catalog")
pathlib.Path("data").mkdir(exist_ok=True)
pathlib.Path("data/ytmusic-albums.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
