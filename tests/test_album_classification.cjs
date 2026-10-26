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

// An impossible or future review date must not establish independent evidence.
context.item=reissue;
for(const checkedAt of ['2099-01-01','2026-02-30','invalid']){
 context.badDates=refs.map(ref=>({...ref,checkedAt}));
 assert.equal(run('assessRelease(item,badDates).verification'),'unconfirmed');
 assert.equal(run('assessRelease(item,badDates).workVerification'),'unconfirmed');
}
context.contradictory=[...refs,...refs.filter(ref=>ref.scope==='release').map(ref=>({...ref,official:false}))];
assert.equal(run('assessRelease(item,contradictory).verification'),'conflict');
assert.equal(run('assessRelease(item,contradictory).visibility'),'unknown');
// Multiple real artists: no Norah reference can confirm a Miles/Jeff edition.
for(const name of ['Miles-Davis','Jeff-Beck']){
 const detail=JSON.parse(readFileSync(`docs/v0.64/${name}-own.json`));
 context.item=detail;
 assert.equal(run('assessRelease(item).verification'),'unconfirmed');
 context.norahOnly=refs.filter(ref=>ref.artistIds.includes(capture.artist_id));
 assert.equal(run('assessRelease(item,norahOnly).workVerification'),'unconfirmed');
 assert.equal(run('assessRelease(item).visibility'),'official');
 context.item={...detail,status:'Bootleg'};
 assert.equal(run('assessRelease(item).visibility'),'excluded');
}
console.log('Future/impossible review dates, contradictory evidence and three real artists passed');
// v0.69: completeness selection is separate from legitimacy and never mixes editions.
context.items=[{...original,id:'incomplete',status:null,'label-info':[],'cover-art-archive':{front:false}},original,reissue];
assert.equal(run('representativeEditions({releases:items})[0].id'),original.id);
assert.equal(run("representativeEditions({releases:items},'incomplete')[0].id"),'incomplete');
assert.equal(run('representativeEditions({releases:items}).length'),3);
assert.equal(context.items[0].id,'incomplete');
context.items=[{...original,id:'without-image','cover-art-archive':{front:false}},original];
assert.equal(run('representativeEditions({releases:items})[0].id'),original.id);
run('coverFailures.set(items[1].id,Date.now())');
assert.equal(run('representativeEditions({releases:items})[0].id'),'without-image');
run('coverFailures.clear()');
// Replay the actual 55+ editions that previously selected a label-less image-less entry.
context.items=releases.filter(r=>r['release-group'].id===original['release-group'].id);
const selected=run('representativeEditions({releases:items})[0]');
assert.equal(selected.status,'Official');
assert.equal(selected['cover-art-archive'].front,true);
assert.ok(selected['label-info'].some(li=>li.label?.name));
assert.equal(assess(selected).verification,'unconfirmed'); // Selection does not authorize a release.
for(const name of ['Miles-Davis','Jeff-Beck']){
 const detail=JSON.parse(readFileSync(`docs/v0.64/${name}-own.json`));
 context.items=[{...detail,id:'incomplete-'+name,status:null,'label-info':[],media:[],'cover-art-archive':{front:false}},detail];
 assert.equal(run('representativeEditions({releases:items})[0].id'),detail.id);
}
console.log('Representative edition: completeness, artwork registration/failure, interaction pin, no mutation and three real artists passed');

// v0.71: a label and its catalog number must match the same label-info entry.
context.item={...reissue,'label-info':[{label:{name:'Blue Note'},'catalog-number':'wrong'},
 {label:{name:'Unrelated'},'catalog-number':'UCCQ-1155/7'}]};
context.pairedRefs=refs.map(ref=>ref.scope==='release'?{...ref,label:'Blue Note'}:ref);
assert.equal(run('assessRelease(item,pairedRefs).verification'),'unconfirmed');
context.item={...reissue,'label-info':[{label:{name:'Blue Note'},'catalog-number':'UCCQ-1155/7'}]};
assert.equal(run('assessRelease(item,pairedRefs).verification'),'confirmed');
for(const sourceUrl of ['https://','https://user:secret@example.org/item','http://example.org/item']){
 context.invalidSources=refs.map(ref=>({...ref,sourceUrl}));
 assert.equal(run('assessRelease(item,invalidSources).verification'),'unconfirmed');
}
context.invalidPublisher=refs.map(ref=>({...ref,publisher:'[unknown]',label:undefined}));
assert.equal(run('assessRelease(item,invalidPublisher).verification'),'unconfirmed');
const reviewed=[
 JSON.parse(readFileSync('docs/v0.64/Miles-Davis-own.json')),
 JSON.parse(readFileSync('docs/v0.64/Jeff-Beck-joint.json')),
 {id:'synthetic-edition-for-work-check', 'release-group':JSON.parse(readFileSync('docs/v0.64/Jeff-Beck-index.json')).find(g=>g.id==='e1f7f19d-ac4a-369f-932c-969d3bc4c13f')},
 JSON.parse(readFileSync('docs/v0.71/healey-web-fields.json')).release,
];
for(const item of reviewed){
 context.item=item;
 assert.equal(run('assessRelease(item).workVerification'),'confirmed',item.title);
 assert.equal(run('assessRelease(item).verification'),'unconfirmed');
 context.negativeRefs=refs.map(ref=>({...ref,official:false}));
 assert.equal(run('assessRelease(item,negativeRefs).workVerification'),'conflict');
 context.item={...item,'release-group':{...item['release-group'],'artist-credit':[{artist:{id:'same-name-different-id'}}]}};
 assert.equal(run('assessRelease(item).workVerification'),'unconfirmed');
 context.item={...item,'release-group':{...item['release-group'],'first-release-date':'1900'}};
 assert.equal(run('assessRelease(item).workVerification'),'conflict');
}
context.item=reviewed[3];
assert.equal(run('assessRelease(item).kind'),'studio');
assert.equal(run('assessRelease(item).labels[0]'),'Arista');
assert.equal(run('assessRelease(item).sources.length'),0); // No edition-authorizing source.
assert.equal(run("artistSearchTerm('ジェフ・ヒーリー・バンド')"),'The Jeff Healey Band');
console.log('New official work references: Miles studio, Beck joint live/compilation, Healey Band studio; no edition escalation, field pairing and source validation passed');

context.item={...reissue,media:[{'track-count':null,format:null}]};
context.missingMedia=refs.map(ref=>({...ref,trackCounts:[null],mediaFormats:[null]}));
assert.equal(run('assessRelease(item,missingMedia).verification'),'unconfirmed');
context.item={...reissue,media:[{'track-count':0,format:'Unknown'}]};
context.missingMedia=refs.map(ref=>({...ref,trackCounts:[0],mediaFormats:['Unknown']}));
assert.equal(run('assessRelease(item,missingMedia).verification'),'unconfirmed');
