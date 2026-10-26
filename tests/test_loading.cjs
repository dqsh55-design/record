const {readFileSync}=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let onScroll;const handlers={};const observers=[],target={isConnected:true};
class Observer{constructor(callback){this.callback=callback;observers.push(this)}disconnect(){}observe(){}}
const context=vm.createContext({URL,console,setTimeout,clearTimeout,Map,Set,
 window:{scrollY:0,addEventListener:(event,handler)=>{handlers[event]=handler;if(event==='scroll')onScroll=handler}},
 IntersectionObserver:Observer,localStorage:{getItem:()=>null},
 document:{getElementById:id=>id==='chronology-more'?target:{addEventListener(){}}}});
vm.runInContext(readFileSync('index.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1],context);
const run=s=>vm.runInContext(s,context);
(async()=>{
 for(const [name,file] of [['Norah Jones','docs/v0.66/artist-index.json'],['Jeff Beck','docs/v0.65/Jeff-Beck-browse-index.json'],['Miles Davis','docs/v0.65/Miles-Davis-browse-index.json']]){
  const groups=JSON.parse(readFileSync(file));context.payload={'release-group-count':groups.length,'release-groups':groups.slice(0,100)};
  context.selected=groups[0]['artist-credit'][0].artist.id;
  run("api=async()=>payload;chronologyOrder='asc';globalThis.state=newChronologyState();state.mode='probe'");
  await run('loadIndexPage(state,selected)');
  assert.equal(run('state.allReady'),groups.length<=100,name);
  assert.equal(run('state.groups.length'),groups.length<=100?groups.length:0,name);
  assert.equal(run('state.mode'),groups.length<=100?'browse':'ranges',name);
  console.log(`${name}: ${groups.length} captured groups, ${groups.length<=100?'one probe completes index':'large probe publishes no prefix; ranges retained'}`);
 }
 context.payload={'release-group-count':2,'release-groups':[{'id':'one','primary-type':'Album','artist-credit':[{artist:{id:'artist'}}]}]};
 run("state=newChronologyState();state.mode='probe';selected='artist'");await assert.rejects(run('loadIndexPage(state,selected)'));assert.equal(run('state.groups.length'),0);
 run("artistId='artist';officialLoading=false;officialError='';globalThis.loads=0;loadOfficialReleases=async()=>{loads++}");
 run('observeReleaseEnd()');assert.equal(observers.length,0); // No loading just because button is on screen.
 context.window.scrollY=100;onScroll();let current=observers.at(-1);current.callback([{isIntersecting:true}]);assert.equal(run('loads'),1);
 current.callback([{isIntersecting:true}]);run('observeReleaseEnd()');assert.equal(run('loads'),1);assert.equal(observers.length,1);
 context.window.scrollY=200;onScroll();const next=observers.at(-1);current.callback([{isIntersecting:true}]);assert.equal(run('loads'),1);next.callback([{isIntersecting:true}]);assert.equal(run('loads'),2);
 context.window.scrollY=300;onScroll();current=observers.at(-1);run('chronologyGeneration++');current.callback([{isIntersecting:true}]);assert.equal(run('loads'),2);
 context.window.scrollY=400;onScroll();current=observers.at(-1);context.window.scrollY=350;onScroll();current.callback([{isIntersecting:true}]);assert.equal(run('loads'),2);
 run("officialError='offline'");context.window.scrollY=500;onScroll();assert.equal(run('loads'),2);
 run("officialError=''");handlers.wheel({deltaY:200});observers.at(-1).callback([{isIntersecting:true}]);assert.equal(run('loads'),3);
 handlers.touchstart({touches:[{clientY:100}]});handlers.touchmove({touches:[{clientY:50}]});observers.at(-1).callback([{isIntersecting:true}]);assert.equal(run('loads'),4);
 console.log('Auto load: downward intent, one batch per intent, no render loop, stale observer/generation rejection, upward cancellation and no automatic error retry passed');
})().catch(e=>{console.error(e);process.exitCode=1});
