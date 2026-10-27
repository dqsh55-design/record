"""Synthetic source contracts; live observations are recorded separately."""
import copy
from datetime import date
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_official_search as probe

TODAY=date(2026,10,27)
W='https://wmg.jp/WillieNelson/discography/album'
B='https://www.bluenote.com/artist/willie-nelson/'
I='https://willienelson.com/collections/music'
P='https://willienelson.com/products/test-album'

def warner(name='Willie Nelson',released='2006.08.23'):
    return f'<p class="x_artistName">{name}</p><a href="/WillieNelson/discography/3355"><h3>Test Atlantic Album</h3><p class="x_releaseInfo">{released} 発売</p><span>ALBUM</span></a>'

def blue(year='2009',name='Willie Nelson'):
    return f'<h1>{name}</h1><div class="release-entry" data-released-year="{year}"><h5 class="post-name">Test Classic - <a href="{B}">{name}</a></h5></div>'

class FixtureTransport:
    def __init__(self):
        self.calls=[];self.pages={I:'<a href="/products/test-album">Test Product</a><a href="https://evil.test/products/fake">Fake</a>',W:warner(),B:blue(),P:'<h1>Test Product</h1><h2>Album Details</h2><p>Release Date: 6/1/1996</p><script type="application/ld+json">{"@type":"Product","name":"Test Product","vendor":"Willie Nelson","datePublished":"1996-06-01"}</script>'};self.failed={}
    def __call__(self,url):
        self.calls.append(url)
        if url in self.failed:return {'url':url,'status':self.failed[url],'httpStatus':403},''
        body=self.pages[url]
        return {'url':url,'status':'ok','sourceSha256':hashlib.sha256(body.encode()).hexdigest(),'allowOrigin':''},body

class OfficialProbe(unittest.TestCase):
    def test_public_catalog_and_source_policies_are_byte_identical(self):
        expected={'data/official-catalog.json':'a46e3366162c7f9a3d858646bfdb5dc36c557cf00e9546388a75f9c81f53646d','data/official-realtime.json':'6ecda71a8b1a1358b670718d426dadc74397a98be41655cd83b5a403137b2bb0','data/official-sources.json':'7122b8e0c5313532555780744ba5d10871f6b43c33344049b3df27fc3795851b'}
        for path,digest in expected.items():self.assertEqual(hashlib.sha256((probe.ROOT/path).read_bytes()).hexdigest(),digest,path)
        catalog=json.loads((probe.ROOT/'data/official-catalog.json').read_text())
        self.assertEqual(len(catalog['artists']),20);self.assertEqual(sum(len(a['albums']) for a in catalog['artists']),292)
        self.assertFalse(any(a['name']=='Willie Nelson' for a in catalog['artists']))
        self.assertEqual(sum(bool(a.get('listeningLink')) for art in catalog['artists'] for a in art['albums']),6)

    def test_generic_directory_discovery_needs_no_willie_identity_or_album_registration(self):
        from datetime import datetime,timezone
        sys.path.insert(0,str(probe.ROOT))
        from server.search import SourceError
        calls=[]
        def fetch(source):
            calls.append(source['url'])
            if source['url']=='https://www.bluenote.com/artists/':
                return '<h5 class="post-name"><a href="/artist/willie-nelson/">Willie Nelson</a></h5>'
            if source['url']==B:return blue()
            raise SourceError('not_found','404')
        result=probe.probe_directories('Willie Nelson',fetch=fetch,clock=lambda:datetime(2026,10,27,tzinfo=timezone.utc).timestamp())
        self.assertFalse(result['perArtistAnchorsConfigured'])
        self.assertEqual(len(result['verifiedWorks']),1)
        self.assertEqual(result['verifiedWorks'][0]['year'],'2009')
        self.assertEqual(result['verifiedWorks'][0]['title'],'Test Classic')
        self.assertIn('https://www.bluenote.com/artists/',calls)
        self.assertIn(B,calls)

    def test_existing_common_adapters_approve_only_two_dated_official_listings(self):
        transport=FixtureTransport();result=probe.probe('ウィリー・ネルソン',transport,TODAY)
        self.assertEqual(result['status'],'confirmed_partial');self.assertEqual(len(result['verifiedWorks']),2)
        self.assertEqual(result['discoveredProductCount'],1)
        self.assertEqual(result['heldCandidates'][0]['status'],'unconfirmed')
        for w in result['verifiedWorks']:
            self.assertTrue(w['officialReleaseConfirmed']);self.assertTrue(w['experimentalOnly'])
            self.assertEqual(w['artist'],'Willie Nelson');self.assertTrue(w['label'])
            self.assertEqual(w['sourceSha256'],hashlib.sha256(transport.pages[w['evidenceSourceUrl']].encode()).hexdigest())
        self.assertFalse(result['publicCatalogModified']);self.assertFalse(result['realtimePagesImplemented'])

    def test_wrong_artist_future_or_current_year_only_are_held(self):
        transport=FixtureTransport();transport.pages[W]=warner('Other Artist');transport.pages[B]=blue('2026')
        result=probe.probe('Willie Nelson',transport,TODAY);self.assertEqual(result['verifiedWorks'],[])
        transport.pages[W]=warner(released='2027.01.01');transport.pages[B]=blue(name='Other Artist')
        self.assertEqual(probe.probe('Willie Nelson',transport,TODAY)['verifiedWorks'],[])

    def test_shopify_product_vendor_and_article_timestamp_cannot_certify_album(self):
        transport=FixtureTransport();accepted,held=probe.inspect_product({'title':'Test Product','sourceUrl':P},transport.pages[P],TODAY)
        self.assertEqual(accepted,[]);self.assertEqual(held['status'],'unconfirmed')

    def test_complete_music_release_can_be_verified_but_missing_issuer_and_future_cannot(self):
        node={'@type':'MusicAlbum','name':'A Real Album','byArtist':{'name':'Willie Nelson'},'albumReleaseType':'https://schema.org/AlbumRelease','albumRelease':{'@type':'MusicRelease','url':P,'datePublished':'2001-01-01','recordLabel':{'name':'Test Official Label'}}}
        def parse(value):return probe.inspect_product({'title':'Test','sourceUrl':P},'<script type="application/ld+json">'+json.dumps(value)+'</script>',TODAY)[0]
        self.assertEqual(len(parse(node)),1)
        bad=copy.deepcopy(node);bad['albumRelease']['recordLabel']={};self.assertEqual(parse(bad),[])
        bad=copy.deepcopy(node);bad['albumRelease']['datePublished']='2099-01-01';self.assertEqual(parse(bad),[])
        bad=copy.deepcopy(node);bad['byArtist']['name']='Other Artist';self.assertEqual(parse(bad),[])

    def test_access_failure_is_not_reported_as_no_official_albums(self):
        transport=FixtureTransport();transport.failed={u:'blocked' for u in [I,W,B]}
        result=probe.probe('Willie Nelson',transport,TODAY)
        self.assertEqual(result['status'],'retrieval_failed');self.assertEqual(result['verifiedWorks'],[])
        self.assertTrue(all(s['status']=='blocked' for s in result['sources']))

    def test_unknown_artist_does_not_guess_domains_or_contact_a_search_api(self):
        transport=FixtureTransport();result=probe.probe('Unknown Name',transport,TODAY)
        self.assertEqual(result['status'],'unsupported_probe_artist');self.assertEqual(transport.calls,[])

    def test_url_boundary_and_redirect_rejection(self):
        for url in ['http://willienelson.com/products/test','https://willienelson.com.evil.test/products/test','https://user@willienelson.com/products/test','https://willienelson.com/products/test?fetch=private','https://127.0.0.1/products/test','https://willienelson.com/products/test#x']:
            self.assertFalse(probe.approved_url(url));self.assertEqual(probe.ProbeTransport()(url)[0]['status'],'unsafe_source')
        with self.assertRaises(ValueError):probe.NoRedirect().redirect_request(None,None,302,'',{},'https://evil.test')

    def test_budget_exhaustion_stops_requests(self):
        with patch.object(probe,'build_opener') as opener:
            info,body=probe.ProbeTransport(limit=0,access_policy=type('FixturePolicy',(),{'permits':lambda self,host:True})())(I)
            self.assertEqual(info['status'],'budget_exhausted');self.assertEqual(body,'');opener.assert_not_called()

    def test_403_blocks_further_requests_to_same_host_without_retry(self):
        with patch.object(probe,'build_opener') as opener:
            opener.return_value.open.side_effect=HTTPError(I,403,'Forbidden',{},BytesIO())
            client=probe.ProbeTransport(access_policy=type('FixturePolicy',(),{'permits':lambda self,host:True})());self.assertEqual(client(I)[0]['status'],'blocked')
            self.assertEqual(client(P)[0]['status'],'blocked');self.assertEqual(opener.return_value.open.call_count,1)

    def test_cors_header_observation_is_exact_and_not_a_browser_success_claim(self):
        self.assertTrue(probe.cors_readable('*'));self.assertTrue(probe.cors_readable(probe.ORIGIN))
        for value in ['', 'null', probe.ORIGIN+'.evil.test',probe.ORIGIN+', https://other.test']:
            self.assertFalse(probe.cors_readable(value))

    def test_report_escapes_source_text_and_does_not_display_held_works(self):
        result=probe.probe('Willie Nelson',FixtureTransport(),TODAY)
        result['verifiedWorks'][0]['title']='<script>evil()</script>'
        html=probe.render_report(result)
        self.assertNotIn('<script>',html);self.assertIn('&lt;script&gt;',html)
        self.assertNotIn('Test Product',html);self.assertIn('公開目次には未登録',html)
        self.assertIn('このHTMLを開いた時に再調査はしません',html)

if __name__=='__main__':unittest.main()
