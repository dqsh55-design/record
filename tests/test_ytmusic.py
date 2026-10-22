import json
from ytmusicapi import YTMusic

music = YTMusic(location='JP', language='ja')
results = music.search('Miles Davis Kind of Blue', filter='albums', limit=20)
items = []
for a in results:
    if 'Kind of Blue' not in a.get('title',''):
        continue
    aid = a.get('browseId')
    if not aid:
        continue
    detail = music.get_album(aid)
    items.append({'title':detail.get('title'), 'artists':detail.get('artists'), 'year':detail.get('year'), 'album_url':'https://music.youtube.com/browse/'+aid, 'tracks':len(detail.get('tracks',[]))})
print(json.dumps(items,ensure_ascii=False,indent=2))
if not items:
    raise SystemExit('No matching album found')
