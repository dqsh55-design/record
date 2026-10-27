"""Offline contracts: common rules must prove issuer, artist, album and release."""
import copy
from datetime import date
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import generate_official_catalog as g
TODAY=date(2026,10,27)


def blue(name='Artist A',slug='artist-a',year='2024',title='Album One'):
    return '<h1>'+name+'</h1><div class="release-entry" data-released-year="'+year+'"><h5 class="post-name">'+title+' - <a href="https://www.bluenote.com/artist/'+slug+'/">'+name+'</a></h5></div>'


def warner(title='Album One',released='2020.05.24',category='ALBUM',artist='Artist A'):
    return '<p class="module__artistName">'+artist+'</p><a href="/artist-a/discography/1"><h3>'+title+'</h3><p class="module__releaseInfo">'+released+' 発売</p><span>'+category+'</span></a>'


def structured(**patches):
    album={'@type':'MusicAlbum','name':'Album One','byArtist':{'name':'Artist A'},'albumReleaseType':'https://schema.org/AlbumRelease','albumRelease':{'@type':'MusicRelease','url':'https://www.norahjones.com/albums/one','datePublished':'2020-01-01','recordLabel':{'name':'Actual Label'}}}
    album.update(patches)
    return '<script type="application/ld+json">'+json.dumps({'@graph':[album]})+'</script>'


class OfficialGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.config=json.loads((ROOT/'data/official-generation.json').read_text())
        self.source={'id':'test-source','provider':'blue-note','artist':{'id':'record:artist-a','name':'Artist A','aliases':['アーティストA']},'host':'www.bluenote.com','url':'https://www.bluenote.com/artist/artist-a/','releasePath':r'/artist/artist-a/?'}
        self.config['sources']=[self.source]
        self.config['discovery']=[]
        self.catalog={'version':1,'artists':[]}

    def run_generate(self,html,base=None):
        return g.generate(base or self.catalog,self.config,lambda source:html,TODAY)

    def test_registers_artist_and_album_without_album_review_or_musicbrainz(self):
        out,report=self.run_generate(blue())
        self.assertEqual(report['added'],1)
        artist=out['artists'][0]
        self.assertEqual(artist['id'],'record:artist-a')
        album=artist['albums'][0]
        self.assertTrue(album['official'])
        self.assertEqual(album['label'],'Blue Note Records')
        self.assertIsNone(album['year'])
        self.assertEqual(album['generationProof']['listedReleaseYear'],'2024')
        self.assertEqual(album['generationProof']['artistId'],artist['id'])
        self.assertEqual(self.catalog['artists'],[])

    def test_identical_adapter_works_for_second_artist_with_settings_only(self):
        other=copy.deepcopy(self.source)
        other.update(id='other',artist={'id':'record:other','name':'Other Artist'},url='https://www.bluenote.com/artist/other/',releasePath=r'/artist/other/?')
        self.config['sources'].append(other)
        out,report=g.generate(self.catalog,self.config,lambda s:blue(s['artist']['name'],s['url'].rstrip('/').split('/')[-1]),TODAY)
        self.assertEqual(report['added'],2)
        self.assertEqual(len(out['artists']),2)
        self.assertNotEqual(out['artists'][0]['albums'][0]['id'],out['artists'][1]['albums'][0]['id'])

    def test_idempotent_and_preserves_existing_metadata(self):
        first,_=self.run_generate(blue())
        second,report=self.run_generate(blue(),first)
        self.assertEqual(first,second)
        self.assertEqual(report['added'],0)
        second['artists'][0]['albums'][0]['year']='1999'
        third,_=self.run_generate(blue(),second)
        self.assertEqual(third,second)

    def test_blue_artist_mismatch_guest_wrong_link_or_uncertain_release_held(self):
        for html in [blue(name='Wrong Artist'),blue(slug='wrong'),blue(year='2026'),blue(year='2099'),blue(year=''),blue(title='Band Record - Band')]:
            with self.subTest(html=html):
                out,report=self.run_generate(html)
                self.assertEqual(out,self.catalog)
                self.assertEqual(report['errorCount'],1)

    def test_unknown_provider_and_spoofed_hosts_never_requested(self):
        for patch_source in [{'provider':'unknown'},{'host':'www.bluenote.com.evil.test'},{'url':'https://user@www.bluenote.com/artist/artist-a/'},{'url':'http://www.bluenote.com/artist/artist-a/'}]:
            config=copy.deepcopy(self.config)
            config['sources'][0].update(patch_source)
            with self.subTest(patch=patch_source):
                out,report=g.generate(self.catalog,config,lambda source:self.fail('unapproved request'),TODAY)
                self.assertEqual(out,self.catalog)
                self.assertEqual(report['errorCount'],1)

    def test_disabled_and_failed_sources_preserve_prior_catalog(self):
        first,_=self.run_generate(blue())
        self.source.update(enabled=False,disabledReason='403')
        out,report=g.generate(first,self.config,lambda s:self.fail('disabled request'),TODAY)
        self.assertEqual(out,first)
        self.assertEqual(report['sources'][0]['status'],'disabled')
        self.source['enabled']=True
        def unavailable(source):raise RuntimeError('HTTP 403')
        out,report=g.generate(first,self.config,unavailable,TODAY)
        self.assertEqual(out,first)
        self.assertEqual(report['errorCount'],1)

    def use_warner(self):
        self.source.update(provider='warner-japan',host='wmg.jp',url='https://wmg.jp/artist-a/discography',releasePath=r'/artist-a/discography/\d+')

    def test_warner_album_past_release_and_edition_deduplication(self):
        self.use_warner()
        html=warner(title='Album One&lt;SHM-CD&gt;')+warner(title='Album One&lt;LP&gt;')
        out,report=self.run_generate(html)
        self.assertEqual(report['added'],1)
        self.assertEqual(out['artists'][0]['albums'][0]['title'],'Album One')

    def test_warner_unsupported_media_future_or_invalid_date_rejected(self):
        self.use_warner()
        for html in [warner(category='映像'),warner(released='2099.01.01'),warner(released='2026.02.30'),warner(artist='Different Artist'),warner().replace('/artist-a/discography/1','https://evil.test/album')]:
            out,report=self.run_generate(html)
            self.assertEqual(out,self.catalog)
            self.assertEqual(report['errorCount'],1)

    def use_jsonld(self):
        self.source.update(provider='artist-official',host='www.norahjones.com',url='https://www.norahjones.com/albums/one',releasePath=r'/albums/[^/]+')

    def test_generic_jsonld_requires_album_artist_issuer_and_release_evidence(self):
        self.use_jsonld()
        out,report=self.run_generate(structured())
        self.assertEqual(report['added'],1)
        self.assertEqual(out['artists'][0]['albums'][0]['label'],'Actual Label')
        for html in [structured(byArtist={'name':'Other Artist'}),structured(albumReleaseType='SingleRelease'),structured(albumRelease={}),structured(albumRelease={'@type':'MusicRelease','recordLabel':{'name':'unknown'},'datePublished':'2020-01-01'}),'<a href="/albums/one">Plausible Album</a>',structured().replace('2020-01-01','2099-01-01')]:
            with self.subTest(html=html):
                out,report=self.run_generate(html)
                self.assertEqual(out,self.catalog)
                self.assertEqual(report['errorCount'],1)

    def test_no_partial_addition_when_source_contains_malformed_record(self):
        self.use_jsonld()
        html=structured()+structured(byArtist={'name':'Wrong Artist'})
        out,report=self.run_generate(html)
        self.assertEqual(report['added'],1)
        self.assertEqual(report['sources'][0]['held'],1)
        self.assertEqual(len(out['artists'][0]['albums']),1)

    def test_existing_artist_cannot_be_duplicated_under_another_id(self):
        base={'version':1,'artists':[{'id':'original','name':'Artist A','albums':[]}]}
        out,report=self.run_generate(blue(),base)
        self.assertEqual(out,base)
        self.assertEqual(report['errorCount'],1)

    def test_real_catalog_generated_entries_keep_valid_proofs(self):
        catalog=json.loads((ROOT/'data/official-catalog.json').read_text())
        generated=[(artist,album) for artist in catalog['artists'] for album in artist['albums'] if album.get('verificationMethod')]
        self.assertGreaterEqual(len(generated),12)
        for artist,album in generated:
            proof=album['generationProof']
            self.assertEqual(proof['artistId'],artist['id'])
            self.assertEqual(proof['sourceUrl'],album['sourceUrl'])
            self.assertIn(proof['rule'],g.ADAPTERS)
            self.assertRegex(proof['sourceSha256'],r'^[a-f0-9]{64}$')
            self.assertIsNone(album['year'])

    def test_index_discovers_new_artist_without_per_artist_registration(self):
        self.config['sources']=[]
        self.config['discovery']=[dict(id='index',provider='blue-note',host='www.bluenote.com',url='https://www.bluenote.com/artists/',artistPath=r'/artist/[a-z-]+/?',maxNewArtistsPerRun=1)]
        index='<h5 class="post-name"><a href="/artist/artist-a/">Artist A</a></h5><h5 class="post-name"><a href="https://evil.test/artist/b/">Wrong</a></h5><h5 class="post-name"><a href="/artist/other/">Other Artist</a></h5>'
        calls=[]
        def fetch(source):
            calls.append(source['url'])
            return index if source['url'].endswith('/artists/') else blue(source['artist']['name'],source['url'].rstrip('/').split('/')[-1])
        out,report=g.generate(self.catalog,self.config,fetch,TODAY)
        self.assertEqual(report['added'],1)
        self.assertEqual(out['artists'][0]['id'],'record:blue-note:artist-a')
        self.assertIn('officialDiscovery',out['artists'][0])
        self.assertEqual(len(calls),2)
        second,second_report=g.generate(out,self.config,fetch,TODAY)
        self.assertEqual(second_report['added'],1)
        self.assertEqual(second['artists'][0],out['artists'][0])
        self.assertEqual(len(second['artists']),2)
        third,third_report=g.generate(second,self.config,fetch,TODAY)
        self.assertEqual(third,second)
        self.assertEqual(third_report['added'],0)

    def test_index_failure_has_no_untrusted_fallback(self):
        self.config['sources']=[]
        self.config['discovery']=[dict(id='index',provider='blue-note',host='evil.test',url='https://evil.test/artists/',artistPath=r'/artist/.*',maxNewArtistsPerRun=2)]
        out,report=g.generate(self.catalog,self.config,lambda s:self.fail('unapproved index request'),TODAY)
        self.assertEqual(out,self.catalog)
        self.assertEqual(report['errorCount'],1)

    def test_cli_refuses_to_overwrite_public_input(self):
        path=ROOT/'data/official-catalog.json'
        before=path.read_bytes()
        for option in ['--output','--report']:
            with patch.object(sys,'argv',['generator','--catalog',str(path),option,str(path)]),self.assertRaises(SystemExit):
                g.main()
        self.assertEqual(path.read_bytes(),before)

if __name__=='__main__':unittest.main()
