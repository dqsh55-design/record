// Captured real MB responses are replayed here. This is NOT a live HTTP test.
const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const script=readFileSync('index.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
const context=vm.createContext({URL,console,setTimeout,clearTimeout,Date,Map,Set,localStorage:{getItem:()=>null},document:{getElementById:()=>({addEventListener(){}})}});
vm.runInContext(script,context);
const run=s=>vm.runInContext(s,context);
const target='selected-artist';
const credit=(id,name=id)=>({name,artist:{id,name}});
context.target=target;
context.credit=credit;
run('artistId=target;render=()=>{}');
for(const [credits,expected] of [
 [undefined,'pending'],[null,'pending'],[[],'pending'],[[credit(target)],'own'],
 [[credit(target,'別の表記')],'own'],[[credit('homonym','selected-artist')],'pending'],
 [[credit(target),credit('collaborator')],'joint'],[[credit('collaborator'),credit(target)],'joint'],
 [[credit(target),credit(target)],'own'],[[credit(target),{name:'Unknown'}],'pending'],
 [[credit(target),' & '],'pending'],[[credit('band')],'pending']]){
 context.credits=credits;assert.equal(run('creditIdentity(credits)'),expected);
}
// Edition credits override work credits, including explicit empty/malformed credits.
context.row={id:'edition','release-group':{'artist-credit':[credit(target)]}};
assert.equal(run('releaseAttribution(row).kind'),'own');
assert.equal(run('releaseAttribution(row).source'),'作品');
context.row['artist-credit']=[credit('other')];
assert.equal(run('releaseAttribution(row).kind'),'pending');
context.row['artist-credit']=[];
assert.equal(run('releaseAttribution(row).kind'),'pending');
const performance={media:[{tracks:[{title:'One',recording:{id:'recording',relations:[{type:'instrument',artist:{id:target},attributes:['guitar']}]}}]}]};
context.performance=performance;
run("editionDetails.set('edition',performance)");
assert.equal(run('releaseAttribution(row).kind'),'pending'); // No edition credit, cannot assert a mere guest.
context.row['artist-credit']=[credit('other')];
assert.equal(run('releaseAttribution(row).kind'),'participation');
assert.equal(run('performanceEvidence(performance).length'),1);
for(const type of ['producer','composer','member of band','instrumental arranger','tribute','performance']){
 context.role=type;
 run('performance.media[0].tracks[0].recording.relations[0].type=role');
 assert.equal(run('releaseAttribution(row).kind'),'pending',type);
}
run("performance.media[0].tracks[0].recording.relations[0].type='instrument'");
run("performance.media[0].tracks[0].recording.relations[0].artist.id='other'");
assert.equal(run('releaseAttribution(row).kind'),'pending');
run('performance.media[0].tracks[0].recording.relations[0].artist.id=target');
context.row['artist-credit']=[credit(target),credit('other')];
assert.equal(run('releaseAttribution(row).kind'),'joint'); // Performance does not erase formal joint credit.
run("creditScope='credited'");assert.equal(run('matchesCreditScope(row)'),true);
run("creditScope='own'");assert.equal(run('matchesCreditScope(row)'),false);
run("creditScope='joint'");assert.equal(run('matchesCreditScope(row)'),true);
run("creditScope='participation'");assert.equal(run('matchesCreditScope(row)'),false);
run("creditScope='all'");assert.equal(run('matchesCreditScope(row)'),true);
run('performance.media[0].tracks.push(performance.media[0].tracks[0])');
assert.equal(run('performanceEvidence(performance).length'),1);
console.log('Generated credit tests: MBID identity, aliases, homonyms, joint credits, incomplete credits, edition precedence, role allowlist, evidence deduplication and scopes passed');

const report=JSON.parse(readFileSync('docs/v0.64/live-report.json'));
for(const artist of report.artists){
 assert.equal(artist.error,undefined,artist.artist);
 const name=artist.artist.replaceAll(' ','-');
 const groups=JSON.parse(readFileSync(`docs/v0.64/${name}-index.json`));
 context.groups=groups;
 context.artist=artist;
 run('artistId=artist.artist_id');
 const counts=run("groups.reduce((out,g)=>{const k=creditIdentity(g['artist-credit']);out[k]=(out[k]||0)+1;return out},{})");
 console.log(`${artist.artist}: captured index ${groups.length} groups, credit counts ${JSON.stringify(counts)} (replayed, not live)`);
 for(const [label,expected] of [['own','own'],['joint','joint'],['guest','participation']]){
  const release=JSON.parse(readFileSync(`docs/v0.64/${name}-${label}.json`));
  context.row=release;
  run('editionDetails.delete(row.id)');
  assert.equal(run('releaseAttribution(row).kind'),label==='guest'?'pending':expected,`${name} ${label} before recording lookup`);
  run('editionDetails.set(row.id,row)');
  assert.equal(run('releaseAttribution(row).kind'),expected,`${name} ${label}`);
  const result=run('releaseAttribution(row)');
  console.log(`${artist.artist}: ${release.title} => ${result.kind}, ${result.evidence.length} recording evidence entries`);
 }
 // Membership itself is not an album credit or proof of playing on an album.
 const relations=JSON.parse(readFileSync(`docs/v0.64/${name}-artist-relations.json`));
 const band=relations.relations.find(r=>r.type==='member of band'&&r.artist?.type==='Group')?.artist;
 if(band){context.band=band;assert.equal(run("creditIdentity([{artist:band}])"),'pending');assert.equal(run("creditIdentity([{artist:band}],band.id)"),'own');}
}
assert(script.includes('inc=artist-credits&limit=100'));
assert(script.includes('inc=labels+media+artist-credits&limit=100'));
assert(script.includes('artist-rels+recording-level-rels'));
console.log('Captured Miles Davis / Jeff Beck own, joint, performance and band-separation regressions passed');
