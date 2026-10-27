"""Prototype integration and strict official-source safety contracts."""
from datetime import datetime,timezone
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.robotparser import RobotFileParser
sys.path.insert(0,str(Path(__file__).resolve().parent))
from realtime_fixtures import make_service,Pages,fixture_config,blue_page
from server.search import OfficialSearch,OfficialTransport,SourceError,POLICY_RESTRICTED_HOSTS
from server.prototype import prototype_app
from scripts.configure_public_api import configure
ROOT=Path(__file__).resolve().parents[1]

class OnDemandPrototype(unittest.TestCase):
    def test_no_artists_or_works_registered_and_all_old_direct_links_remain(self):
        import hashlib
        self.assertEqual(hashlib.sha256((ROOT/'data/official-catalog.json').read_bytes()).hexdigest(),'a46e3366162c7f9a3d858646bfdb5dc36c557cf00e9546388a75f9c81f53646d')
        catalog=json.loads((ROOT/'data/official-catalog.json').read_text())
        self.assertEqual(len(catalog['artists']),20);self.assertEqual(sum(len(a['albums']) for a in catalog['artists']),292)
        self.assertEqual(sum(bool(a.get('listeningLink')) for art in catalog['artists'] for a in art['albums']),6)
        self.assertNotIn('Willie Nelson',[a['name'] for a in catalog['artists']])

    def test_willie_discovered_without_identity_registration_with_year_label_and_url(self):
        config=fixture_config();self.assertNotIn('Willie Nelson',[a['name'] for a in config['identities']])
        pages=Pages();pages.pages['https://www.bluenote.com/artists/']+='<h5 class="post-name"><a href="/artist/willie-nelson/">Willie Nelson</a></h5>'
        pages.pages['https://www.bluenote.com/artist/willie-nelson/']=blue_page('Willie Nelson','willie-nelson',['American Classic'])
        service=OfficialSearch(config,':memory:',fetch=pages);self.addCleanup(service.cache.close)
        result=service.search('Willie Nelson');album=result['artist']['albums'][0]
        self.assertEqual((album['title'],album['year'],album['label']),('American Classic','2002','Blue Note Records')) # Fixture year, not a live assertion.
        self.assertEqual(album['sourceUrl'],'https://www.bluenote.com/artist/willie-nelson/')
        self.assertNotIn('listeningLink',album);before=len(pages.calls)
        self.assertTrue(service.search('Willie Nelson')['cache']['hit']);self.assertEqual(len(pages.calls),before)

    def test_bilingual_directory_labels_remain_bound_to_same_artist_url(self):
        config=fixture_config();pages=Pages()
        pages.pages['https://wmg.jp/artistlist']='<a href="/WillieNelson">ウィリー・ネルソン</a><a href="/WillieNelson">Willie Nelson</a><a href="/other-artist">別の人</a>'
        pages.pages['https://wmg.jp/WillieNelson/discography/album']='<p class="x_artistName">ウィリー・ネルソン</p><a href="/WillieNelson/discography/3355"><h3>Atlantic Album</h3><p class="x_releaseInfo">2006.08.23 発売</p><span>ALBUM</span></a>'
        service=OfficialSearch(config,':memory:',fetch=pages);self.addCleanup(service.cache.close)
        result=service.search('Willie Nelson')
        self.assertEqual(result['artist']['albums'][0]['title'],'Atlantic Album')
        self.assertIn('ウィリー・ネルソン',result['artist']['aliases'])
        self.assertNotIn('別の人',result['artist']['aliases'])
        self.assertTrue(service.search('ウィリー・ネルソン')['cache']['hit'])

    def test_api_year_comes_from_release_evidence_for_all_three_fixture_artists(self):
        service,pages=make_service();self.addCleanup(service.cache.close)
        for name in ['Jimi Hendrix','Miles Davis','New Artist']:
            for album in service.search(name)['artist']['albums']:
                proof=album['generationProof'];self.assertEqual(album['year'],(proof.get('listedReleaseDate') or proof['listedReleaseYear'])[:4])

    def test_v088_cached_null_year_is_restored_without_extending_proof_expiry(self):
        service,_=make_service();self.addCleanup(service.cache.close);r=service.search('Norah Jones')
        expiry=r['artist']['albums'][0]['validUntilUnix'];r['artist']['albums'][0]['year']=None
        with service.cache.db:service.cache.db.execute('UPDATE verified SET body=?',(json.dumps(r),))
        out=service.search('Norah Jones');self.assertEqual(out['artist']['albums'][0]['year'],'2002')
        self.assertEqual(out['artist']['albums'][0]['validUntilUnix'],expiry)

    def test_concurrent_searches_keep_independent_verified_cache_entries(self):
        from concurrent.futures import ThreadPoolExecutor
        service,_=make_service();self.addCleanup(service.cache.close)
        names=['Norah Jones','Miles Davis','New Artist']*4
        with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(service.search,names))
        self.assertTrue(all(r['artist']['albums'] for r in results))
        ids={service.search(n)['artist']['id'] for n in names}
        self.assertEqual(len(ids),3)
        self.assertTrue(all(service.search(n)['cache']['hit'] for n in names))

    def test_cache_cannot_override_a_verified_release_year(self):
        service,_=make_service();self.addCleanup(service.cache.close);r=service.search('Norah Jones')
        for a in r['artist']['albums']:a['year']='2099'
        with service.cache.db:service.cache.db.execute('UPDATE verified SET body=?',(json.dumps(r),))
        self.assertIsNone(service.cache.get('Norah Jones'))

    def test_warner_discovered_sources_use_album_only_path(self):
        service,pages=make_service();self.addCleanup(service.cache.close)
        service.search('Miles Davis')
        self.assertIn('https://wmg.jp/miles-davis/discography/album',pages.calls)
        self.assertNotIn('https://wmg.jp/miles-davis/discography',pages.calls)

    def test_terms_restricted_hosts_never_contact_network(self):
        with patch('server.search.build_opener') as opener:
            transport=OfficialTransport(POLICY_RESTRICTED_HOSTS)
            for host in POLICY_RESTRICTED_HOSTS:
                with self.assertRaises(SourceError) as error:transport(dict(host=host,url='https://'+host+'/'))
                self.assertEqual(error.exception.kind,'policy_restricted')
            opener.assert_not_called()

    def test_robots_disallow_stops_before_album_fetch(self):
        transport=OfficialTransport({'wmg.jp'},access_policy=type('FixturePolicy',(),{'permits':lambda self,host:True})());parser=RobotFileParser();parser.parse(['User-agent: *','Disallow: /private'])
        transport.robots['wmg.jp']=(transport.clock()+3600,parser)
        with patch('server.search.build_opener') as opener:
            with self.assertRaises(SourceError) as error:transport(dict(host='wmg.jp',url='https://wmg.jp/private'))
            self.assertEqual(error.exception.code,'robots_disallow');opener.assert_not_called()

    def test_policy_failure_is_distinct_from_missing_release(self):
        config=fixture_config()
        def deny(source):raise SourceError('policy_restricted','terms_review_required')
        service=OfficialSearch(config,':memory:',fetch=deny);self.addCleanup(service.cache.close)
        out=service.search('Jimi Hendrix');self.assertEqual(out['status'],'policy_restricted');self.assertEqual(out['artist']['albums'],[])

    def test_hybrid_configuration_is_explicit_and_public_file_stays_catalog(self):
        html=(ROOT/'index.html').read_text()
        self.assertIn('name="record-search-mode" content="catalog"',html)
        self.assertIn('name="record-api-base" content=""',html)
        prepared=configure(html,'https://api.example.test',mode='hybrid')
        self.assertIn('name="record-search-mode" content="hybrid"',prepared)
        self.assertIn('https://api.example.test/',prepared)
        with self.assertRaises(ValueError):configure(html,'https://api.test',mode='guess')

    def test_local_prototype_serves_only_home_catalog_and_existing_api(self):
        service,_=make_service();self.addCleanup(service.cache.close);app=prototype_app(service)
        def get(path):
            status=[];body=b''.join(app({'REQUEST_METHOD':'GET','PATH_INFO':path,'QUERY_STRING':''},lambda s,h:status.append(s)))
            return status[0],body
        self.assertIn(b'record-search-mode" content="hybrid',get('/')[1])
        self.assertEqual(get('/data/official-catalog.json')[1],(ROOT/'data/official-catalog.json').read_bytes())
        for path in ['/server/search.py','/.git/config','/../data/official-realtime.json']:self.assertEqual(get(path)[0],'404 Not Found')

if __name__=='__main__':unittest.main()
