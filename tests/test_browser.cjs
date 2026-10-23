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
