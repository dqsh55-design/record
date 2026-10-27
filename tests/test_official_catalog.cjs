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

// A reviewed official outbound chain can open an album. Names or saved URLs alone cannot.
context.norah=context.catalog.artists.find(a=>a.name==='Norah Jones');
context.visions=context.norah.albums.find(a=>a.title==='Visions');
assert.equal(run('confirmedListeningLink(norah,visions).url'),context.visions.listeningLink.url);
for(const patch of [{artistId:'wrong'},{albumId:'wrong'},{albumTitle:'Other Album'},{linkPageTitle:'Other Artist - Visions'},{officialSourceUrl:'https://evil.test/'},{officialLinkUrl:'https://evil.test/Visions'},{checkedAt:'2099-01-01'},{reviewNote:''},{targetSha256:'bad'},{url:'https://music.youtube.com/watch?v=abc'},{url:'https://music.youtube.com/playlist?list=PLuserlist'},{url:'https://music.youtube.com.evil.test/playlist?list=OLAK5uy_test'},{target:{...context.visions.listeningLink.target,title:'Other Album'}},{target:{...context.visions.listeningLink.target,artist:'Other Artist'}},{target:{...context.visions.listeningLink.target,type:'music.song'}},{target:{...context.visions.listeningLink.target,url:'https://music.youtube.com/browse/MPREb_other'}}]){
 context.patch=patch;
 assert.equal(run('confirmedListeningLink(norah,{...visions,listeningLink:{...visions.listeningLink,...patch}})'),null,JSON.stringify(patch));
}
assert.equal(run('confirmedListeningLink(norah,{...visions,official:false})'),null);
assert.equal(run('confirmedListeningLink(norah,norah.albums.find(a=>a.title==="Come Away With Me"))'),null);
context.miles=context.catalog.artists.find(a=>a.name==='Miles Davis');
assert.equal(run('confirmedListeningLink(miles,miles.albums.find(a=>a.title==="Kind Of Blue"))'),null);
run('verifiedLinks[visions.id]="https://music.youtube.com/browse/MPREb_unreviewed"');
assert.equal(run('confirmedListeningLink(norah,visions).url'),context.visions.listeningLink.url);
console.log('Reviewed official outbound album links, wrong identity/source/target rejection and search fallback passed');

assert.equal(run('confirmedListeningLink(miles,miles.albums.find(a=>a.title==="Birth Of The Cool")).url'),context.miles.albums.find(a=>a.title==='Birth Of The Cool').listeningLink.url);

context.bill=context.catalog.artists.find(a=>a.name==='Bill Frisell');
context.dreams=context.bill.albums.find(a=>a.title==='In My Dreams');
assert.equal(run('confirmedListeningLink(bill,dreams).url'),context.dreams.listeningLink.url);
for(const bad of ['https://billfrisell.lnk.to.evil.test/InMyDreams','https://fake.billfrisell.lnk.to/InMyDreams']){
 context.bad=bad;assert.equal(run('confirmedListeningLink(bill,{...dreams,listeningLink:{...dreams.listeningLink,officialLinkUrl:bad}})'),null);
}

// New genres use the same reviewed catalog, alias lookup and exact-host rules.
for(const name of ['The Beatles','Led Zeppelin','Black Sabbath','Metallica','Kraftwerk','Daft Punk','David Bowie','Michael Jackson','Ryuichi Sakamoto']){
 const artist=context.catalog.artists.find(a=>a.name===name);
 for(const alias of [name,...artist.aliases]){context.query=alias;assert.equal(run('catalogArtist(query).id'),artist.id)}
}
for(const name of ["B’z","B'z","B'z","ビーズ"]){context.query=name;assert.equal(run('catalogArtist(query)'),undefined)}
context.daft=context.catalog.artists.find(a=>a.name==='Daft Punk');context.discovery=context.daft.albums[0];
assert.equal(run('confirmedListeningLink(daft,discovery).url'),context.discovery.listeningLink.url);
assert.equal(run('confirmedListeningLink(daft,daft.albums[1])'),null);
for(const bad of ['https://daftpunk.lnk.to.evil.test/Discovery','https://fake.daftpunk.lnk.to/Discovery']){
 context.bad=bad;assert.equal(run('confirmedListeningLink(daft,{...discovery,listeningLink:{...discovery.listeningLink,officialLinkUrl:bad}})'),null);
}
for(const host of ['www.thebeatles.com','discography.ledzeppelin.com','www.metallica.com','daftpunk.com','www.daftpunk.com','www.commmons.com']){
 context.bad='https://'+host+'.evil.test/album';assert.equal(run('confirmedCatalogAlbums({albums:[{...discovery,sourceUrl:bad}]}).length'),0);
}
console.log('Nine new artist aliases, approved direct link, search fallbacks and exact host rejection passed');

// A larger official discography retains reviewed links and independent search fallbacks.
for(const title of ['Human After All','Alive 2007']){
 context.album=context.daft.albums.find(a=>a.title===title);
 assert.equal(run('confirmedListeningLink(daft,album).url'),context.album.listeningLink.url);
}
assert.equal(run('confirmedListeningLink(daft,daft.albums.find(a=>a.title==="Alive 1997"))'),null);
assert.equal(context.catalog.artists.reduce((sum,artist)=>sum+artist.albums.length,0),385);

// v0.87 adds genres through the same exact-alias and reviewed-catalog path.
for(const name of ['John Coltrane','Queen','Iron Maiden','Underworld','Madonna','宇多田ヒカル']){
 const artist=context.catalog.artists.find(a=>a.name===name);assert.ok(artist);
 for(const alias of [name,...artist.aliases]){context.query=alias;assert.equal(run('catalogArtist(query).id'),artist.id)}
 context.artist=artist;
 assert.equal(run('confirmedCatalogAlbums(artist).length'),artist.albums.length);
 for(const album of artist.albums){context.album=album;assert.equal(run('confirmedListeningLink(artist,album)'),null)}
}
assert.equal(context.catalog.artists.length,27);

// v0.88 additions pass the existing recognition and multilingual lookup path.
for(const artist of context.catalog.artists.slice(20)){
 context.artist=artist;
 for(const alias of [artist.name,...artist.aliases]){context.query=alias;assert.equal(run('catalogArtist(query).id'),artist.id)}
 assert.equal(run('confirmedCatalogAlbums(artist).length'),artist.albums.length);
 for(const album of artist.albums){context.album=album;assert.equal(run('confirmedListeningLink(artist,album)'),null)}
}
