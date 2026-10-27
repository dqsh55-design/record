const {readFileSync}=require('node:fs');
const vm=require('node:vm'),assert=require('node:assert/strict');
const script=readFileSync('index.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
const context=vm.createContext({URL,console,setTimeout,clearTimeout,Map,Set,localStorage:{getItem:()=>null},document:{getElementById:()=>({addEventListener(){}})}});
vm.runInContext(script,context);
const run=s=>vm.runInContext(s,context);
context.catalog=JSON.parse(readFileSync('data/official-catalog.json'));
run('officialCatalog=catalog');
for(const [query,count] of [['ノラ・ジョーンズ',12],['Norah Jones',12],['マイルスデイビス',26],['Miles Davis',26]]){
 context.query=query;assert.equal(run('confirmedCatalogAlbums(catalogArtist(query)).length'),count);
}
assert.equal(run("catalogArtist('Unknown')"),undefined);
for(const patch of [{official:false},{scope:'release'},{checkedAt:'2099-01-01'},{checkedAt:'2026-02-30'},{sourceUrl:'https://evil.test/official'},{sourceUrl:'javascript:alert(1)'},{sourceUrl:'https://www.bluenote.com.evil.test/'},{sourceUrl:'https://wmg.jp.evil.test/'},{sourceUrl:'https://user@www.bluenote.com/'},{sourceUrl:'https://www.bluenote.com:9999/'},{label:'unknown'},{title:''},{reviewNote:''},{reviewNote:null}]){
 context.patch=patch;assert.equal(run('confirmedCatalogAlbums({albums:[{...catalog.artists[0].albums[0],...patch}]}).length'),0,JSON.stringify(patch));
}
assert.equal(run('confirmedCatalogAlbums({albums:[catalog.artists[0].albums[0],catalog.artists[0].albums[0]]}).length'),1);
// A database Official status or a plausible label cannot create an approved entry.
assert.equal(run("confirmedCatalogAlbums({albums:[{id:'fake',title:'Fake',status:'Official',label:'Columbia'}]}).length"),0);
console.log('Official catalog: Norah then Miles, aliases, missing evidence, unsafe sources, dates, deduplication and no MB promotion passed');
