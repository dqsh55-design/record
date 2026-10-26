// Deterministic transport tests; no external network or real-time sleeps.
const {readFileSync}=require('node:fs');
const vm=require('node:vm'),assert=require('node:assert/strict');
let now=2000000000000,calls=0,fail=false,release;
class Clock extends Date {static now(){return now}}
const context=vm.createContext({URL,console,Date:Clock,AbortController,setTimeout:(f,ms)=>ms===15000?setTimeout(f,ms):(queueMicrotask(f),0),clearTimeout,
 localStorage:{getItem:()=>null},document:{getElementById:()=>({addEventListener(){}})},
 fetch:async()=>{calls++;if(release)await new Promise(r=>release=r);return {ok:!fail,status:fail?503:200,json:async()=>({releases:[{id:'edition'}]})}}});
vm.runInContext(readFileSync('index.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1],context);
const run=s=>vm.runInContext(s,context);
(async()=>{
 release=true;
 const a=run("api('release?artist=A')"),b=run("api('release?artist=A')");
 await new Promise(setImmediate);assert.equal(calls,1);release();release=null;
 const [x,y]=await Promise.all([a,b]);x.releases[0].id='changed';assert.equal(y.releases[0].id,'edition');
 const start=calls;
 for(let i=0;i<20;i++)assert.equal((await run("api('release?artist=A')")).releases[0].id,'edition');
 assert.equal(calls,start); // 20 repeated requests => zero additional HTTP requests.
 await run("api('release?artist=B')");await run("api('release?artist=A&offset=100')");assert.equal(calls,3);
 now+=600001;await run("api('release?artist=A')");assert.equal(calls,4);
 fail=true;await assert.rejects(run("api('failure',{attempts:1})"));
 fail=false;await run("api('failure')");assert.equal(calls,6);
 now-=700000;await run("api('failure')");assert.equal(calls,7); // Backward clock invalidates.
 for(let i=0;i<105;i++)await run(`api('bounded-${i}')`);
 assert.equal(run('apiResponses.size'),100);assert.equal(run('apiRequests.size'),0);
 console.log('API cache: coalescing, independent copies, 20 repeats/0 HTTP, artist/page isolation, expiry, clock rollback, failure recovery and 100-entry limit passed');
})().catch(e=>{console.error(e);process.exitCode=1});
