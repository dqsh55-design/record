"""Synthetic official-page structures for deterministic API/UI tests; no live claims."""
import copy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from server.search import OfficialSearch,SourceError


def blue_page(name,slug,titles):
    return '<h1>'+name+'</h1>'+''.join('<div class="release-entry" data-released-year="2002"><h5 class="post-name">'+title+' - <a href="https://www.bluenote.com/artist/'+slug+'/">'+name+'</a></h5></div>' for title in titles)


def album_json(name,title,url):
    value={'@type':'MusicAlbum','name':title,'byArtist':{'name':name},'albumReleaseType':'https://schema.org/AlbumRelease','albumRelease':{'@type':'MusicRelease','datePublished':'2001-01-01','recordLabel':{'name':'Official Test Issuer'},'url':url}}
    return '<script type="application/ld+json">'+json.dumps(value)+'</script>'


def fixture_config():
    config=json.loads((ROOT/'data/official-realtime.json').read_text())
    config.update(refreshCooldownSeconds=0,negativeCacheSeconds=0)
    # Test only the two functioning directory formats. Sony failures are separate cases.
    config['directories']=[d for d in config['directories'] if d['provider']!='sony-japan']
    for identity in config['identities']:
        identity['sources']=[s for s in identity['sources'] if s['provider']!='sony-japan']
    return config


class Pages:
    def __init__(self):
        self.calls=[]
        self.fail=False
        self.pages={
            'https://www.bluenote.com/artists/':'<h5 class="post-name"><a href="/artist/norah-jones/">Norah Jones</a></h5><h5 class="post-name"><a href="/artist/new-artist/">New Artist</a></h5>',
            'https://wmg.jp/artistlist':'<a href="/miles-davis">マイルス・デイヴィス</a><a href="/new-artist">New Artist</a>',
            'https://www.bluenote.com/artist/norah-jones/':blue_page('Norah Jones','norah-jones',['Come Away With Me','Feels Like Home']),
            'https://www.bluenote.com/artist/new-artist/':blue_page('New Artist','new-artist',['A Newly Discovered Album']),
            'https://wmg.jp/new-artist/discography/album':'<p class="x_artistName">New Artist</p>',
            'https://www.jimihendrix.com/music/':album_json('The Jimi Hendrix Experience','Are You Experienced','https://www.jimihendrix.com/music/are-you-experienced/'),
            'https://www.milesdavis.com/albums/':album_json('Miles Davis','Kind Of Blue','https://www.milesdavis.com/albums/kind-of-blue/'),
            'https://wmg.jp/miles-davis/discography/album':'<p class="x_artistName">マイルス・デイヴィス</p><a href="/miles-davis/discography/18010"><h3>ドゥー・バップ&lt;SHM-CD&gt;</h3><p class="x_releaseInfo">2017.05.24 発売</p><span>ALBUM</span></a>'
        }

    def __call__(self,source):
        self.calls.append(source['url'])
        if self.fail:
            raise SourceError('blocked','403')
        if source['url'] not in self.pages:
            raise SourceError('not_found','404')
        return self.pages[source['url']]


def make_service(path=':memory:',clock=None):
    pages=Pages()
    options={} if clock is None else {'clock':clock}
    return OfficialSearch(fixture_config(),path,fetch=pages,**options),pages
