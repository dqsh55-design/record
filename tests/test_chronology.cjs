// Generated responses: correctness of partial metadata windows, never real API evidence.
const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const script=readFileSync('index.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
// Freeze only the calendar year for these recorded 2026 windows; expiry clocks stay real.
class WindowDate extends Date {getUTCFullYear(){return 2026}}
const context=vm.createContext({URL,console,setTimeout,clearTimeout,Date:WindowDate,Map,Set,localStorage:{getItem:()=>null},document:{getElementById:()=>({addEventListener(){}})}});
vm.runInContext(script,context);
const run=s=>vm.runInContext(s,context);
const group=(id,date)=>({id,title:id,'primary-type':'Album','first-release-date':date,'artist-credit':[{artist:{id:'artist',name:'Artist'}}]});
context.group=group;context.requests=[];
run("render=()=>{};artistId='artist';artistName='Artist'");
const nextTurn=()=>new Promise(resolve=>setImmediate(resolve));
// The recorded search/browse responses are replayed offline, not additional HTTP requests.
for(const name of ['Miles-Davis','Jeff-Beck']){
 const groups=JSON.parse(readFileSync(`docs/v0.65/${name}-browse-index.json`));
 context.recordedGroups=groups;
 for(const order of ['asc','desc']){
  context.order=order;
  const actual=run("chronologyOrder=order;dateRanges().flatMap(range=>orderedGroups(recordedGroups.filter(g=>inDateRange(g,range)))).map(g=>g.id).join(',')");
  const sign=order==='asc'?1:-1;
  const known=groups.filter(g=>g['first-release-date']).sort((a,b)=>sign*a['first-release-date'].localeCompare(b['first-release-date'])||a.id.localeCompare(b.id));
  const unknown=groups.filter(g=>!g['first-release-date']).sort((a,b)=>a.id.localeCompare(b.id));
  assert.equal(actual,[...known,...unknown].map(g=>g.id).join(','));
 }
 console.log(`${name}: recorded full index partitions into disjoint date ranges with exact chronological order and unknown tail`);
}

(async()=>{
 let secondPage,releasePages=0;
 context.mock=async path=>{
  context.requests.push(path);
  const q=new URL('https://example.test/'+path).searchParams;
  if(path.startsWith('release-group?')){
   if(q.get('offset')==='0')return {count:101,'release-groups':Array.from({length:100},(_,i)=>group('work'+i,'1970'))};
   return await new Promise(resolve=>secondPage=resolve);
  }
  releasePages++;
  return {'release-count':101,releases:q.get('offset')==='0'?Array.from({length:100},(_,i)=>({id:'edition'+i,status:'Official',date:'2020'})):[{id:'edition99'},{id:'last',status:'Official',date:'2021'}]};
 };
 run('api=mock');const first=run('loadOfficialReleases(true)');await nextTurn();
 assert.equal(run('officialReleases.length'),0);
 assert.equal(run('chronology.groups.length'),0); // Index prefix cannot leak before its window is complete.
 assert.equal(run('chronology.pending.length'),100);
 secondPage({count:101,'release-groups':[{...group('earliest','1950'),releases:[{id:'unused-reference'}]}]});await first;
 assert.equal(run("'releases' in chronology.groups[0]"),false);
 assert.equal(run("officialReleases[0]['release-group'].id"),'earliest');
 assert.equal(run('chronology.allReady'),false); // Later periods were NOT fetched.
 assert.equal(context.requests.filter(p=>p.startsWith('release-group?')).length,2);
 const original=context.mock;
 context.mock=async path=>{throw Error('offline')};run('api=mock');
 await run('loadOfficialReleases()');assert.equal(run('officialError'),'offline');
 assert.equal(run('officialReleases.length'),100);assert.equal(run('chronology.releaseOffset'),100);
 context.mock=original;run('api=mock');await run('loadOfficialReleases()');
 assert.equal(run('officialReleases.length'),101);assert.equal(run('chronology.cursor'),1);
 assert.equal(releasePages,2);
 console.log('Window completion, an oldest work on page 2, deferred later periods, duplicate editions and release retry passed');

 // Changing counts in an uncommitted later window resets only that window, retaining the prefix.
 run('chronology.cursor=chronology.groups.length');
 let changed=false,windowCalls=0;
 context.mock=async path=>{
  const q=new URL('https://example.test/'+path).searchParams;
  if(path.startsWith('release-group?')){
   windowCalls++;
   if(q.get('offset')==='0')return {count:changed?2:3,'release-groups':[group('eighties','1980')]};
   changed=true;return {count:2,'release-groups':[group('late-eighties','1989')]};
  }
  return {'release-count':1,releases:[{id:'eighties-edition',status:'Official'}]};
 };
 run('api=mock');await run('loadOfficialReleases()');
 assert.match(run('officialError'),/更新/);
 assert.equal(run('chronology.indexOffset'),0);
 assert.equal(run('officialReleases.length'),101);
 await run('loadOfficialReleases()');
 assert.equal(run('officialReleases.length'),102);assert.equal(windowCalls,4);
 console.log('Upstream count changes cannot publish a partial range and restart without losing the visible prefix');

 // Descending and unknown tail use disjoint ranges. Empty ranges are searched, not guessed.
 run('rangeIndexCache.clear();chronologyOrder="desc";chronology=null;officialReleases=[]');
 context.mock=async path=>{
  const q=new URL('https://example.test/'+path).searchParams;
  if(path.startsWith('release-group?')){
   const query=q.get('query');
   const items=query.includes('NOT firstreleasedate')?[group('unknown','')]:query.includes('TO 1979')?[group('old','1951')]:query.includes('TO *')?[group('future','2099'),group('modern','2021')]:[];
   return {count:items.length,'release-groups':items};
  }
  return {'release-count':1,releases:[{id:q.get('release-group'),status:'Official'}]};
 };
 run('api=mock');
 for(let i=0;i<8&&(i===0||run('chronologyHasMore()'));i++)await run('loadOfficialReleases()');
 assert.equal(run("officialReleases.map(r=>r.id).join(',')"),'future,modern,old,unknown');
 assert.equal(run('chronologyHasMore()'),false);
 assert.equal(run("inDateRange(group('partial','1980'),{low:'1980-01-01',high:'1989-12-31'})"),true);
 console.log('Descending, future dates, partial-year boundaries, empty ranges and unknown-year tail passed');

 // A work moved between years must not appear twice across separately completed windows.
 run('rangeIndexCache.clear()');let revised=false;
 context.mock=async path=>{
  const q=new URL('https://example.test/'+path).searchParams;
  if(path.startsWith('release-group?')){
   const before=q.get('query').includes('TO 1979');
   if(before)return {count:revised?0:1,'release-groups':revised?[]:[group('moved','1950')]};
   revised=true;return {count:1,'release-groups':[group('moved','1980')]};
  }
  return {'release-count':1,releases:[{id:'moved-edition',status:'Official'}]};
 };
 run('api=mock');await run('loadOfficialReleases(true)');await run('loadOfficialReleases()');
 assert.equal(run('chronology.restartRequired'),true);assert.equal(run('officialReleases.length'),1);
 run('switchChronology("asc")');await nextTurn();
 assert.equal(run("officialReleases[0]['release-group']['first-release-date']"),'1980');
 console.log('A work moving to another date range cannot create duplicate works; refreshing drops stale window caches');

 // An unavailable search falls back before publishing; browse's page 2 may contain the oldest.
 run('rangeIndexCache.clear();chronology=null;officialReleases=[]');
 let browsePage;
 context.mock=async path=>{
  const q=new URL('https://example.test/'+path).searchParams;
  if(q.has('query'))throw Error('search unavailable');
  if(path.startsWith('release-group?')){
   if(q.get('offset')==='0')return {'release-group-count':2,'release-groups':[group('new','2020')]};
   return await new Promise(resolve=>browsePage=resolve);
  }
  return {'release-count':1,releases:[{id:'oldest-edition',status:'Official'}]};
 };
 run('api=mock');const fallback=run('loadOfficialReleases(true)');await nextTurn();
 assert.equal(run('officialReleases.length'),0);assert.equal(run('chronology.mode'),'browse');
 browsePage({'release-group-count':2,'release-groups':[group('oldest','1950')]});await fallback;
 assert.equal(run("officialReleases[0]['release-group'].id"),'oldest');
 console.log('Search failure safely falls back to a fully completed browse index before any cards are published');
})().catch(error=>{console.error(error);process.exitCode=1});
