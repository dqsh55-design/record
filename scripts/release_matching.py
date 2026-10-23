"""Conservative, auditable release matching. No network or catalog writes on import."""
import re
import unicodedata
from datetime import datetime, timezone


def key(value):
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKC", value or "").casefold())


def supported_group(group):
    return group.get("primary-type") == "Album" and not (
        set(group.get("secondary-types", [])) - {"Live", "Compilation"}
    )


def release_evidence(group, detail, releases, allowed_artists):
    """A group association is a candidate; corroboration must refer to ONE release."""
    allowed = {key(name) for name in allowed_artists}
    artists = [a.get("name", "") for a in detail.get("artists", [])]
    title_matches = bool(key(group.get("title"))) and key(group.get("title")) == key(detail.get("title"))
    artist_matches = bool(artists) and all(key(name) and key(name) in allowed for name in artists)
    tracks = detail.get("tracks") or []
    yt_tracks = [key(t.get("title")) for t in tracks]
    yt_label = detail.get("label") or ""
    evidence = []
    for release in releases:
        labels = [li.get("label", {}).get("name") for li in release.get("label-info", []) if li.get("label")]
        labels = [name for name in labels if name and name.strip().casefold() not in {"[no label]", "[unknown]"}]
        mb_tracks = [key(t.get("title") or t.get("recording", {}).get("title"))
                     for medium in release.get("media", []) for t in medium.get("tracks", [])]
        credits = [a.get("artist", {}).get("name", "") for a in release.get("artist-credit", []) if isinstance(a, dict)]
        # A returned prefix is not a complete album. Compare advertised counts
        # when present, including each disc, before comparing ordered titles.
        complete_yt = detail.get("trackCount", len(tracks)) == len(tracks)
        media = release.get("media") or []
        complete_mb = bool(media) and all(
            m.get("track-count", len(m.get("tracks") or [])) == len(m.get("tracks") or [])
            for m in media)
        complete_mb = complete_mb and release.get("medium-count", len(media)) == len(media)
        same_tracks = bool(yt_tracks) and all(yt_tracks) and complete_yt and complete_mb and yt_tracks == mb_tracks
        same_label = bool(key(yt_label)) and any(key(yt_label) == key(label) for label in labels)
        official = release.get("status", "").casefold() == "official" and bool(labels)
        release_artist = bool(credits) and all(key(name) and key(name) in allowed for name in credits)
        evidence.append({"release_id": release.get("id"), "status": release.get("status"),
                         "date": release.get("date"), "country": release.get("country"),
                         "labels": labels, "catalog_numbers": [li.get("catalog-number") for li in release.get("label-info", []) if li.get("catalog-number")],
                         "source_url": "https://musicbrainz.org/release/" + release.get("id", ""),
                         "track_titles": [t.get("title") or t.get("recording", {}).get("title", "")
                                          for m in media for t in m.get("tracks", [])],
                         "tracklists_complete": complete_yt and complete_mb,
                         "tracklist_match": same_tracks, "label_match": same_label,
                         "artist_match": release_artist,
                         "corroborated": official and same_tracks and same_label and release_artist})
    corroborated = supported_group(group) and title_matches and artist_matches and any(r["corroborated"] for r in evidence)
    return {"version": 1, "checked_at": datetime.now(timezone.utc).isoformat(),
            "status": "corroborated" if corroborated else "candidate",
            "title_match": title_matches, "artist_match": artist_matches,
            "supported_type": supported_group(group), "yt_label": yt_label,
            "yt_track_titles": [t.get("title", "") for t in tracks],
            "releases": evidence,
            "caveat": "Metadata corroboration does not guarantee authorized YouTube Music distribution."}
