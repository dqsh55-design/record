const {readFileSync}=require('node:fs');
const vm=require('node:vm'),assert=require('node:assert/strict');
const script=readFileSync('index.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
const context=vm.createContext({URL,console,setTimeout,clearTimeout,Map,Set,localStorage:{getItem:()=>null},document:{getElementById:()=>({addEventListener(){}})}});
vm.runInContext(script,context);
const run=s=>vm.runInContext(s,context);
context.catalog=JSON.parse(readFileSync('data/official-catalog.json'));
run('officialCatalog=catalog');
for(const query of ['ノラ・ジョーンズ','Norah Jones','マイルスデイビス','Miles Davis','Bill Frisell','ビルフリゼール']){
 context.query=query;const artist=run('catalogArtist(query)');assert.ok(artist,query);
 assert.equal(run('confirmedCatalogAlbums(catalogArtist(query)).length'),artist.albums.length,query+' must show only valid catalog entries');
}
assert.ok(run("catalogArtist('Miles Davis').albums.length")>=26);
assert.ok(run("catalogArtist('Bill Frisell').albums.length")>=4);
for(const artist of context.catalog.artists){context.query=artist.name;assert.equal(run('confirmedCatalogAlbums(catalogArtist(query)).length'),artist.albums.length)}
assert.equal(run("catalogArtist('Unknown')"),undefined);
for(const patch of [{official:false},{scope:'release'},{checkedAt:'2099-01-01'},{checkedAt:'2026-02-30'},{sourceUrl:'https://evil.test/official'},{sourceUrl:'javascript:alert(1)'},{sourceUrl:'https://www.bluenote.com.evil.test/'},{sourceUrl:'https://wmg.jp.evil.test/'},{sourceUrl:'https://user@www.bluenote.com/'},{sourceUrl:'https://www.bluenote.com:9999/'},{label:'unknown'},{title:''},{reviewNote:''},{reviewNote:null}]){
 context.patch=patch;assert.equal(run('confirmedCatalogAlbums({albums:[{...catalog.artists[0].albums[0],...patch}]}).length'),0,JSON.stringify(patch));
}
assert.equal(run('confirmedCatalogAlbums({albums:[catalog.artists[0].albums[0],catalog.artists[0].albums[0]]}).length'),1);
// A database Official status or a plausible label cannot create an approved entry.
assert.equal(run("confirmedCatalogAlbums({albums:[{id:'fake',title:'Fake',status:'Official',label:'Columbia'}]}).length"),0);
console.log('Official catalog: Norah then Miles, aliases, missing evidence, unsafe sources, dates, deduplication and no MB promotion passed');

// Generated entries require complete, matching provenance; a plausible source host alone is insufficient.
context.generated=context.catalog.artists.flatMap(a=>a.albums).find(a=>a.verificationMethod);
context.generatedArtist=context.catalog.artists.find(a=>a.id===context.generated.generationProof.artistId);
for(const patch of [{generationProof:null},{verificationMethod:'unknown'},{generationProof:{...context.generated.generationProof,artistId:'wrong'}},{generationProof:{...context.generated.generationProof,sourceSha256:'bad'}},{generationProof:{...context.generated.generationProof,sourceUrl:'https://wmg.jp/wrong'}}]){
 context.patch=patch;assert.equal(run('confirmedCatalogAlbums({...generatedArtist,albums:[{...generated,...patch}]}).length'),0);
}

// Pages remains the default even when an API URL is present; API mode is explicit.
assert.equal(run('publicSearchMode()'),'catalog');
run(`document.querySelector=selector=>({content:selector.includes('record-api-base')?'https://unused.example/':'catalog'})`);
assert.equal(run('publicSearchMode()'),'catalog');
run(`document.querySelector=()=>({content:'api'})`);
assert.equal(run('publicSearchMode()'),'api');
