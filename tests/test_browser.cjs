const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const html=readFileSync('index.html','utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const storage={};
const context=vm.createContext({URL,console,setTimeout,clearTimeout,Date,Map,Set,localStorage:{getItem:k=>storage[k]||null,setItem:(k,v)=>storage[k]=v},document:{getElementById:()=>({addEventListener(){}})}});
vm.runInContext(script,context);
function run(s){return vm.runInContext(s,context)}
const id='11111111-1111-1111-1111-111111111111';
run(`globalThis.id=${JSON.stringify(id)};globalThis.url='https://music.youtube.com/browse/MPREb_test';`);
assert.equal(run("saveVerification(id,{ytUrl:url,verdict:'matched'})"),false);
assert.equal(run("saveVerification(id,{ytUrl:url,verdict:'matched',ytLabel:'Label',notes:'曲目と発売元を確認'})"),true);
assert.equal(run("getVerification(id,url+'?si=share').ytLabel"),'Label');
assert.equal(run("getVerification(id,url).evidenceSnapshot.source"),'MusicBrainz');
assert.equal(run("getVerification(id,url+'other')"),null);
assert.equal(run("saveVerification(id,{ytUrl:'https://example.com',verdict:'pending'})"),false);
run("verificationRecords[id]={mbReleaseGroup:id,ytUrl:url+'legacy',verdict:'pending'}");
assert.equal(run("getVerification(id,url+'legacy').verdict"),'pending');
context.localStorage.setItem=()=>{throw Error('quota')};
assert.equal(run("saveVerification(id,{ytUrl:url,verdict:'different'})"),false);
assert.equal(run("getVerification(id,url).verdict"),'matched');
assert(!script.includes("||[...ytAlbums,...relatedCatalogAlbums].find(x=>x.artist_check==='matched'&&titleKey"));
console.log('Browser logic: save, validation, canonical URLs, legacy records, evidence, quota rollback passed');
assert.equal(run("Boolean(usableLabel('[no label]'))"),false);
assert.equal(run("Boolean(usableLabel('Columbia'))"),true);
run("releaseEvidenceCache[id]={savedAt:Date.now(),data:{releases:[{status:'Official','label-info':[{label:{name:'[no label]'}}]}]}};");
assert.equal(run("cachedOfficialEvidence(id)"),'unconfirmed');
console.log('Unknown publisher placeholders cannot establish official-release evidence');

// Album links must identify one album, with no credentials, alternate port or suffix.
for(const value of ['https://music.youtube.com/browse/MPREb_',
 'https://music.youtube.com/browse/MPREb_test/extra',
 'https://user@music.youtube.com/browse/MPREb_test',
 'https://music.youtube.com:444/browse/MPREb_test',
 'https://music.youtube.com/playlist?list=OLAK5uy_',
 'https://music.youtube.com.evil.test/browse/MPREb_test']) {
 assert.equal(run(`albumUrl(${JSON.stringify(value)})`),false,value);
}
assert.equal(run("albumUrl('https://music.youtube.com/playlist?list=OLAK5uy_test&si=share')"),true);
context.localStorage.setItem=(k,v)=>storage[k]=v;
run("releaseEvidenceCache[id]={savedAt:123,data:{'release-count':101,releases:[{id:'edition','label-info':[{label:{name:'Label'}}]}]}};");
assert.equal(run("saveVerification(id,{ytUrl:url,verdict:'matched',ytLabel:'Label',notes:'checked'})"),true);
assert.equal(run("getVerification(id,url).evidenceSnapshot.releaseCount"),101);
run("delete releaseEvidenceCache[id]");
assert.equal(run("saveVerification(id,{ytUrl:url,verdict:'different'})"),true);
assert.equal(run("getVerification(id,url).evidenceSnapshot.releases[0].id"),'edition');
assert.equal(run("getVerification(id,url).mbReleaseGroup"),id);
// Import a backup larger than the former silent snapshot-drop threshold.
context.FileReader=class {readAsText(file){this.result=file;this.onload()}};
context.alert=()=>{};
run("render=()=>{}");
const backup={format:'RECORD-verification-v1',records:{[id]:{mbReleaseGroup:id,
 ytUrl:'https://music.youtube.com/browse/MPREb_restore',verdict:'matched',
 evidenceSnapshot:{releases:[{notes:'x'.repeat(200001)}]}}}};
context.backup=JSON.stringify(backup);
run('importVerificationRecords(backup)');
assert.equal(run("getVerification(id,'https://music.youtube.com/browse/MPREb_restore').evidenceSnapshot.releases[0].notes.length"),200001);
console.log('Strict album URLs, snapshot preservation and large-backup restore passed');

assert.equal(run("saveVerification(id,{ytUrl:url,verdict:'matched',ytLabel:' [no label] ',notes:'checked'})"),false);

const fresh=new Date().toISOString();
context.fresh=fresh;
assert.equal(run("automaticState({id:'a',automatic_verification:{version:1,album_id:'a',checked_at:fresh,status:'supported'}})"),'supported');
assert.equal(run("automaticState({id:'b',automatic_verification:{version:1,album_id:'a',checked_at:fresh,status:'supported'}})"),'insufficient');
assert.equal(run("automaticState({id:'a',automatic_verification:{version:1,album_id:'a',checked_at:'2000-01-01',status:'supported'}})"),'insufficient');
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.style={}}
 append(...items){this.children.push(...items)}
}
context.document.createElement=tag=>new Element(tag);
context.info=new Element('div');
run("appendAutomaticEvidence({id:'a'},info)");
assert.equal(context.info.children[0].textContent,'情報不足：正規盤は未確認');
assert.equal(context.info.children[1].tag,'details');
context.info=new Element('div');
run(`appendAutomaticEvidence({id:'a',automatic_verification:{version:1,album_id:'a',checked_at:fresh,status:'different',youtube:{labels:[],tracks:[{title:'<script>unsafe</script>'}],complete:false},candidates:[{release_id:'edition',checks:{order:'different'},tracks:[{title:'Other'}]}]}},info)`);
const allText=node=>[node.textContent,...(node.children||[]).flatMap(c=>allText(c))];
assert(allText(context.info).some(t=>t.includes('曲順：不一致')));
assert(allText(context.info).some(t=>t.includes('レーベル：未取得')));
assert(allText(context.info).some(t=>t.includes('<script>unsafe</script>')));
assert(!context.info.innerHTML);
console.log('Automatic evidence: album binding, expiry, missing metadata, mismatch and safe text rendering passed');

assert.equal(run("releaseVisibility({status:'Official','label-info':[]})"),'official');
assert.equal(run("releaseVisibility({})"),'unknown');
for(const status of ['Bootleg','Pseudo-Release','Promotion']){
 context.releaseStatus=status;
 assert.equal(run('releaseVisibility({status:releaseStatus})'),'excluded');
}
console.log('Release-first policy preserves incomplete official records and separates explicit non-official editions');

context.detail={media:[{position:2,'track-count':2,tracks:[{position:2,title:'Fourth'},{position:1,title:'Third'}]},{position:1,'track-count':2,tracks:[{position:1,number:'A1',title:'First'}]},{position:3,'track-count':1}]};
assert.equal(run('editionTrackText(detail)'), 'ディスク1 · A1. First\nディスク1：曲目情報が不足しています（1 / 2曲）。\nディスク2 · 1. Third\nディスク2 · 2. Fourth\nディスク3：曲目は未登録です。\nディスク3：曲目情報が不足しています（0 / 1曲）。');
assert.equal(context.detail.media[0].position,2);
console.log('Edition tracks: disc/track ordering, printed vinyl numbers and incomplete metadata passed');

// v0.61: release identity, conservative direct links, and transactional saving.
assert.equal(run("uniqueReleaseIds([{id:'one'},{id:'one'},{id:'two'}]).length"),2);
assert.equal(run("saveEditionLink(id,'https://example.com')"),false);
assert.equal(run("saveEditionLink(id,url+'?si=tracking')"),true);
assert.equal(run("editionLinks[id].url"),run('url'));
context.localStorage.setItem=()=>{throw Error('quota')};
assert.equal(run("saveEditionLink(id,'')"),false);
assert.equal(run('editionLinks[id].url'),run('url'));
context.localStorage.setItem=(k,v)=>storage[k]=v;
assert.equal(run("saveEditionLink(id,'')"),true);
assert.equal(run('editionLinks[id]'),undefined);
run(`artistName='Artist';ytAlbums=[{id:'MPREb_test',url,artist_check:'matched',automatic_verification:{version:2,album_id:'MPREb_test',checked_at:fresh,status:'supported',youtube:{source:url,title:'Album',year:'2001',artists:['Artist'],complete:true,tracks:[{title:'One'}]},candidates:[{release_id:id,status:'supported',title:'Album',date:'2001',checks:Object.fromEntries(['official','title','artist','year','label','count','titles','order'].map(k=>[k,'match']))}]}}]`);
assert.equal(run("supportedEditionLink({id,title:'Album',date:'2001'}).id"),'MPREb_test');
assert.equal(run("supportedEditionLink({id:'other',title:'Album',date:'2001'})"),undefined);
assert.equal(run("supportedEditionLink({id,title:'Album',date:'2002'})"),undefined);
assert.equal(run("listeningAlbumUrl('https://music.youtube.com/playlist?list=OLAK5uy_test')"),false);
assert.equal(run("listeningAlbumUrl('https://music.youtube.com/watch?v=abcdefghijk')"),false);
run("ytAlbums[0].url='https://music.youtube.com/browse/MPREb_other'");
assert.equal(run("supportedEditionLink({id,title:'Album',date:'2001'})"),undefined);
run("ytAlbums[0].url=url;artistName='Different Artist'");
assert.equal(run("supportedEditionLink({id,title:'Album',date:'2001'})"),undefined);
run("artistName='Artist';ytAlbums[0].automatic_verification.checked_at='2000-01-01'");
assert.equal(run("supportedEditionLink({id,title:'Album',date:'2001'})"),undefined);
console.log('v0.61: release ID deduplication, edition binding, stale evidence and storage rollback passed');

(async()=>{
 context.originalApi=run('api');context.pending=[];
 run("api=()=>new Promise(resolve=>pending.push(resolve));artistId=id");
 const older=run('loadOfficialReleases(true)'),newer=run('loadOfficialReleases(true)');
 context.pending[1]({releases:[{id:'new'}],'release-count':1});await newer;
 context.pending[0]({releases:[{id:'stale'}],'release-count':1});await older;
 assert.equal(run('officialReleases[0].id'),'new');
 assert.equal(run('officialOffset'),1);
 run('api=originalApi');
 console.log('Overlapping resets cannot append stale releases or alter pagination');
 context.AbortController=AbortController;
 context.setTimeout=fn=>setTimeout(fn,1);
 context.fetch=async(url,{signal})=>({ok:true,status:200,json:()=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(Object.assign(new Error('aborted'),{name:'AbortError'}))))});
 await assert.rejects(run("fetchJSONWithTimeout('https://musicbrainz.org/ws/2/artist')"),/タイムアウト/);
 let calls=0;
 context.fetch=async()=>{calls++;return {ok:false,status:429}};
 await assert.rejects(run("api('artist?query=test')"),/アクセス制限中.*429/);
 assert.equal(calls,3);
 context.fetch=async()=>({ok:true,status:200,json:async()=>({artists:[]})});
 assert.equal((await run("api('artist?query=retry')")).artists.length,0);
 console.log('Network safety: response-body timeout, bounded 429 retries and queue recovery passed');
})().catch(error=>{console.error(error);process.exitCode=1});
