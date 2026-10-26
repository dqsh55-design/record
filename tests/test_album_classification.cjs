// Real MB snapshots + explicitly reviewed official facts, replayed offline.
const {readFileSync,writeFileSync}=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const script=readFileSync('index.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
const context=vm.createContext({URL,console,setTimeout,clearTimeout,Map,Set,localStorage:{getItem:()=>null},document:{getElementById:()=>({addEventListener(){}})}});
vm.runInContext(script,context);
const run=s=>vm.runInContext(s,context);
const refs=JSON.parse(readFileSync('data/discography-references.json')).references;
context.refs=refs;run('discographyReferences=refs');
const capture=JSON.parse(readFileSync('docs/v0.66/capture.json'));
const snapshots=capture.group_ids.map(id=>JSON.parse(readFileSync(`docs/v0.66/${id}-editions.json`)));
const releases=snapshots.flatMap(d=>d.releases.map(r=>({...r,'release-group':d.group})));
const find=id=>structuredClone(releases.find(r=>r.id===id));
const assess=r=>{context.item=r;return run('assessRelease(item)')};
const original=find('c88138cf-00f3-3c70-8757-3bbe0e4713d1');
const reissue=find('dd00e0df-dd7e-48af-8b13-921bf505167f');
const analogue=find('c766c537-9eef-4005-ad35-b6b0a1bd5712');
const cases=[
 ['original studio',original,'studio','official','unconfirmed','2002-02-26'],
 ['official live',find('93f9b391-3836-477e-bc3b-9d350684fb99'),'live','official','unconfirmed','2021-04-16'],
 ['official compilation',find('36469a3c-5ed7-460d-b2f8-c78208589fad'),'compilation','official','unconfirmed','2010-11-03'],
 ['official reissue',reissue,'studio','official','confirmed','2002-02-26'],
 ['licensed specialist imprint stays visible',analogue,'studio','official','unconfirmed','2002-02-26'],
 ['missing status on a named label',find('608d22ac-be83-453e-97e8-6fc607a30908'),'studio','unknown','unconfirmed','2002-02-26'],
 ['missing status and label',find('03deeefc-9b7a-4655-a819-11cc992c8b45'),'studio','unknown','unconfirmed','2002-02-26'],
 ['withdrawn remains pending',find('6e0af97b-723b-4b0c-a410-dc257a373071'),'studio','unknown','unconfirmed','2002-02-26'],
];
const report=[];
for(const [name,r,kind,visibility,verification,date] of cases){
 const result=assess(r);
 assert.equal(result.kind,kind,name);assert.equal(result.visibility,visibility,name);
 assert.equal(result.verification,verification,name);assert.equal(result.originalDate,date,name);
 assert.equal(result.workVerification,'confirmed',name);
 report.push({name,releaseId:r.id,...JSON.parse(JSON.stringify(result))});
}
assert.equal(assess(reissue).releaseDate,'2022-05-27');
assert.equal(assess(reissue).edition,'reissue');
assert.deepEqual([...assess(reissue).labels],['Blue Note']);
assert.deepEqual([...assess(reissue).publishers],['ユニバーサル ミュージック合同会社']);
assert.deepEqual([...assess(original).publishers],[]); // No reissue publisher inheritance.
assert.deepEqual([...assess(analogue).labels],['Analogue Productions']);
// Documentary work confirmation cannot authorize other editions of the same work.
assert.equal(assess(original).edition,'unconfirmed');
for(const patch of [{date:'2022'}, {'label-info':[]}, {media:[{'track-count':44}]},
 {'artist-credit':[{artist:{id:'homonym'}}]}, {'release-group':{...reissue['release-group'],id:'different-work'}},
 {id:'different-release'}, {'label-info':[{label:{name:'Blue Note'},'catalog-number':'different'}]}]){
 assert.equal(assess({...reissue,...patch}).verification,'unconfirmed');
}
for(const status of ['Bootleg','Promotion','Pseudo-Release','Withdrawn','Cancelled']){
 const result=assess({...reissue,status});assert.equal(result.verification,'conflict');assert.equal(result.visibility,'unknown');
}
// Missing independent evidence is unconfirmed, never a bootleg inference.
assert.equal(assess({...original,status:null,'label-info':[]}).visibility,'unknown');
for(const r of releases.filter(r=>r.status==='Bootleg'))assert.equal(assess(r).visibility,'excluded');
context.item={...original,'release-group':{...original['release-group'],'first-release-date':'1999'}};
assert.equal(run('assessRelease(item).workVerification'),'conflict');
context.item={...original,'release-group':{...original['release-group'],'first-release-date':''}};
assert.equal(run('assessRelease(item).workVerification'),'unconfirmed');
// No title keywords, well-known label allowlist, or artist-specific code.
for(const secondary of [['Remix'],['Soundtrack'],['DJ-mix'],['Interview'],['Demo'],['Audiobook']]){
 context.item={...original,'release-group':{...original['release-group'],'secondary-types':secondary}};
 assert.equal(run('albumKind(item["release-group"])'),'other');
}
context.item={...original,title:'Greatest Hits Live Bootleg Deluxe 2022',status:'Official'};
assert.equal(run('assessRelease(item).kind'),'studio');assert.equal(run('assessRelease(item).visibility'),'official');
context.item={'primary-type':'Album','secondary-types':['Compilation','Live']};assert.equal(run('albumKind(item)'),'live-compilation');
// Exact identity is preserved even when barcode, catalog, titles, or tracks coincide.
context.items=[original,original,reissue,analogue,{...original,id:'another-edition'},
 {...original,id:'another-work','release-group':{...original['release-group'],id:'same-title-other-work'}},
 {id:'unknown-a',title:original.title},{id:'unknown-b',title:original.title}];
assert.equal(run('uniqueReleaseIds(items).length'),7);
assert.equal(run('releaseWorks(items).length'),4);
assert.equal(run('releaseWorks(items)[0].releases.length'),4);
// Detailed status/label takes precedence, without stealing the work's original year.
context.item=original;
run("editionDetails.set(item.id,{status:null,date:'2030','label-info':[], 'release-group':{'first-release-date':'2030'}})");
assert.equal(run('releaseVisibility(item)'),'unknown');
assert.equal(run('assessRelease(releaseRecord(item)).originalDate'),'2002-02-26');
assert.equal(run('assessRelease(releaseRecord(item)).releaseDate'),'2030');
run('editionDetails.clear()');
// Metamorphic regression: change every artist/title/ID, retaining the same relationships.
const renamed=structuredClone(reissue),renamedRefs=structuredClone(refs);
const replaceIds=obj=>JSON.parse(JSON.stringify(obj).replaceAll(capture.artist_id,'some-other-artist').replaceAll(reissue.id,'some-other-edition').replaceAll(reissue['release-group'].id,'some-other-work').replaceAll('Norah Jones','Another Artist'));
context.item=replaceIds(renamed);context.renamedRefs=replaceIds(renamedRefs);
assert.equal(run('assessRelease(item,renamedRefs).verification'),'confirmed');
if(process.env.RECORD_CLASSIFICATION_REPORT)writeFileSync(process.env.RECORD_CLASSIFICATION_REPORT,JSON.stringify({mode:'offline replay of real MB responses and reviewed official facts',cases:report},null,2)+'\n');
console.log(`${cases.length} real edition cases + identity, incomplete/conflicting evidence, secondary types, detail precedence and artist-independent regressions passed`);
// Real source conflict: MB Not Too Late says 2006, Blue Note's discography says 2007.
const index=JSON.parse(readFileSync('docs/v0.66/artist-index.json'));
context.item={id:'generated-release-for-index-check','release-group':index.find(g=>g.id==='1155e2ce-f1b2-394a-b23a-22406c8782a3')};
assert.equal(run('assessRelease(item).workVerification'),'conflict');
assert.equal(run('workYearText(item)'),'2006年（MB登録・初回発売年は未確認）');
assert.equal(run('assessRelease(item).originalDate'),'2006'); // No silent rewrite of chronology.
// Incomplete/malformed references and mismatched format cannot confirm an edition.
context.item=reissue;
assert.equal(run('assessRelease(item,[null,{},"bad"]).verification'),'unconfirmed');
context.invalidRefs=refs.map(ref=>({...ref,artistIds:'not-an-array'}));
assert.equal(run('assessRelease(item,invalidRefs).verification'),'unconfirmed');
context.item={...reissue,media:reissue.media.map(m=>({...m,format:'Digital Media'}))};
assert.equal(run('assessRelease(item).verification'),'unconfirmed');
console.log('Recorded first-year conflict and malformed/format evidence regressions passed');

assert.equal(run("sameArtistIds(['a','a'],['a','b'])"),false);
assert.equal(run("sameArtistIds(['a','b'],['b','a'])"),true);
