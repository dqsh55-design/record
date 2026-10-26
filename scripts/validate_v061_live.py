"""Opt-in live checks; never used as an offline test or a link-verification bypass.
Run: python scripts/validate_v061_live.py (requires requests).
CAA redirects are reported without following destinations outside the policy.
"""
import requests,json,time,datetime
from pathlib import Path
s=requests.Session();s.headers['User-Agent']='RECORD-v0.61-validation (https://github.com/dqsh55-design/record)'
root=Path(__file__).resolve().parents[1]/'docs/v0.61';root.mkdir(exist_ok=True)
report={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'targets':[]}
def mb(path,params):
 
 for attempt in range(3):
  time.sleep(1.2*(attempt+1));r=s.get('https://musicbrainz.org/ws/2/'+path,params={**params,'fmt':'json'},timeout=30)
  if r.status_code not in (429,502,503):break
 r.raise_for_status();return r.json()
for name in ['Jeff Beck','Miles Davis']:
 a=mb('artist',{'query':'artist:"'+name+'"','limit':10})['artists'];a=next(x for x in a if x['name']==name)
 d=mb('release',{'artist':a['id'],'inc':'labels+release-groups+media','limit':100})
 (root/(name.replace(' ','-')+'-releases.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2))
 report['targets'].append({'artist':name,'id':a['id'],'total':d['release-count'],'first_page':len(d['releases']),'unique_ids':len({x['id'] for x in d['releases']})})
 if name=='Jeff Beck':
  r=next(x for x in d['releases'] if x.get('cover-art-archive',{}).get('front'))
  c=s.get('https://coverartarchive.org/release/'+r['id'],timeout=30,allow_redirects=False)
  report['cover_metadata']={'release_id':r['id'],'title':r['title'],'status':c.status_code,'redirect':c.headers.get('location')}
  image=s.get('https://coverartarchive.org/release/'+r['id']+'/front-250',timeout=30,allow_redirects=False)
  report['cover_image']={'status':image.status_code,'redirect':image.headers.get('location'),'redirect_followed':False}
  if c.status_code==200:
   (root/'cover-metadata.json').write_text(json.dumps(c.json(),indent=2));im=s.get('https://coverartarchive.org/release/'+r['id']+'/front-250',timeout=30);report['cover_image']={'status':im.status_code,'final_url':im.url,'content_type':im.headers.get('content-type')}
modern=mb('release',{'query':'release:"Modern Jazz Trumpets" AND arid:'+report['targets'][1]['id'],'limit':100})
(root/'Modern-Jazz-Trumpets.json').write_text(json.dumps(modern,ensure_ascii=False,indent=2))
for release in modern['releases']:
 detail=mb('release/'+release['id'],{'inc':'recordings+labels+artist-credits+release-groups+url-rels'})
 (root/(release['id']+'.json')).write_text(json.dumps(detail,ensure_ascii=False,indent=2))
report['modern']=[{k:r.get(k) for k in ['id','title','date','country','disambiguation','barcode','label-info','media']} for r in modern['releases']]
try:
 r=s.get('https://music.youtube.com/search?q=Jeff%20Beck%20Blow%20by%20Blow',timeout=30);report['youtube_music']={'status':r.status_code,'bypass_attempted':False}
except requests.RequestException as e:report['youtube_music']={'error':type(e).__name__,'proxy_tunnel_status':403 if '403 Forbidden' in str(e) else None,'upstream_status_unconfirmed':True,'bypass_attempted':False}
(root/'live-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
