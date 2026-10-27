"""Measure real browser CORS from the Pages origin, without changing the live site."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from probe_official_search import ORIGIN, SOURCES

TARGETS=[s['url'] for s in SOURCES]+['https://willienelson.com/products/spirit']
PROBE_URL=ORIGIN+'/record/__official_source_probe__'
FETCH_SCRIPT="""async url=>{
 const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),12000);
 try{
  const response=await fetch(url,{mode:'cors',credentials:'omit',redirect:'error',signal:controller.signal,cache:'no-store'});
  if(!response.ok)return {status:'http_error',httpStatus:response.status,readable:false};
  if(response.type==='opaque')return {status:'opaque_response',readable:false};
  const reader=response.body.getReader();let size=0;const chunks=[];
  while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;
   if(size>2000000){await reader.cancel();return {status:'response_too_large',readable:false}}chunks.push(value)}
  const data=new Uint8Array(size);let offset=0;for(const chunk of chunks){data.set(chunk,offset);offset+=chunk.length}
  const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',data))).map(v=>v.toString(16).padStart(2,'0')).join('');
  return {status:'readable',readable:true,httpStatus:response.status,bytes:size,sourceSha256:hash};
 }catch(error){return {status:error.name==='AbortError'?'timeout':'browser_fetch_error',readable:false}}
 finally{clearTimeout(timer)}
}"""


def measure(samples=2):
    report={'format':'RECORD-browser-cors-probe-v1','checkedAt':datetime.now(timezone.utc).isoformat(),'origin':ORIGIN,'method':'Chromium page fetch with normal CORS; Pages origin document fulfilled locally, official responses are live','credentialMode':'omit','corsDisabled':False,'samples':[],'interpretation':'readable proves transport only, never official album release; a fetch error alone cannot distinguish CORS, blocking and network failure'}
    with sync_playwright() as p:
        executable=os.environ.get('RECORD_CHROMIUM') or shutil.which('google-chrome') or shutil.which('chromium')
        browser=p.chromium.launch(**({'executable_path':executable} if executable else {}))
        report['browserVersion']=browser.version
        context=browser.new_context();page=context.new_page();console=[];unexpected=[]
        page.on('console',lambda msg:console.append(msg.text) if msg.type=='error' else None)
        def route(r):
            if r.request.url==PROBE_URL:
                r.fulfill(body='<!doctype html><meta charset="utf-8"><title>RECORD isolated CORS probe</title>',content_type='text/html');return
            if r.request.url in TARGETS and r.request.method=='GET':r.continue_();return
            unexpected.append(r.request.url);r.abort()
        page.route('**/*',route);page.goto(PROBE_URL)
        for sample in range(samples):
            for url in TARGETS:
                console.clear();result=page.evaluate(FETCH_SCRIPT,url)
                result.update(url=url,sample=sample+1,corsConsoleObserved=any('cors' in m.lower() for m in console))
                report['samples'].append(result)
        report['unexpectedRequests']=unexpected
        context.close();browser.close()
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args()
    result=measure();Path(args.output).parent.mkdir(parents=True,exist_ok=True);Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
