import json
import traceback
from ytmusicapi import YTMusic

music = YTMusic(location="JP", language="ja")
queries = ["Miles Davis", "Kind of Blue", "Miles Davis Kind of Blue"]
for query in queries:
    print("\nQUERY:", query, flush=True)
    for category in [None, "albums"]:
        try:
            kwargs = {"limit": 10}
            if category:
                kwargs["filter"] = category
            results = music.search(query, **kwargs)
            print("FILTER:", category or "all", "COUNT:", len(results), flush=True)
            print(json.dumps([{"title": x.get("title"), "resultType": x.get("resultType"), "browseId": x.get("browseId"), "artists": x.get("artists")} for x in results[:5]], ensure_ascii=False), flush=True)
        except Exception as exc:
            print("ERROR:", repr(exc), flush=True)
            traceback.print_exc()
print("Diagnostic completed; empty results are not treated as a successful catalog connection.")
