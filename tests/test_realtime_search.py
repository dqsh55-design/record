import copy
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import urlencode

sys.path.insert(0,str(Path(__file__).resolve().parent))
from realtime_fixtures import make_service,fixture_config,Pages,album_json
from server.search import OfficialSearch,OfficialTransport,SourceError
from server.app import create_app

NOW=datetime(2026,10,27,tzinfo=timezone.utc).timestamp()

class RealtimeSearchTests(unittest.TestCase):
    def setUp(self):
        self.now=NOW
        self.service,self.pages=make_service(clock=lambda:self.now)
        self.addCleanup(self.service.cache.close)

    def test_three_artists_verified_on_demand_without_prebuilt_catalog(self):
        for query,title in [('ジミ・ヘンドリックス','Are You Experienced'),('ノラ・ジョーンズ','Come Away With Me'),('マイルス・デイビス','Kind Of Blue')]:
            with self.subTest(query=query):
                result=self.service.search(query)
                self.assertEqual(result['status'],'confirmed')
                self.assertIn(title,[a['title'] for a in result['artist']['albums']])
                self.assertFalse(result['cache']['hit'])
                self.assertTrue(all(a['official'] and a['generationProof'] and a['sourceUrl'].startswith('https:') for a in result['artist']['albums']))
        self.assertFalse(any('musicbrainz' in url or 'official-catalog.json' in url for url in self.pages.calls))

    def test_new_artist_is_discovered_without_identity_or_album_registration(self):
        result=self.service.search('New Artist')
        self.assertIn('A Newly Discovered Album',[a['title'] for a in result['artist']['albums']])
        self.assertTrue(result['artist']['id'].startswith('record:official:'))

    def test_successful_results_reused_and_aliases_share_cache(self):
        first=self.service.search('ノラジョーンズ')
        count=len(self.pages.calls)
        second=self.service.search('Norah Jones')
        self.assertTrue(second['cache']['hit'])
        self.assertEqual(first['artist']['albums'],second['artist']['albums'])
        self.assertEqual(len(self.pages.calls),count)

    def test_cache_persists_across_service_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'cache.sqlite3'
            service,pages=make_service(path,clock=lambda:self.now)
            first=service.search('Miles Davis')
            service.cache.close()
            restarted,pages=make_service(path,clock=lambda:self.now)
            self.addCleanup(restarted.cache.close)
            pages.fail=True
            result=restarted.search('マイルスデイビス')
            self.assertTrue(result['cache']['hit'])
            self.assertEqual(result['artist']['albums'],first['artist']['albums'])
            self.assertEqual(pages.calls,[])

    def test_official_appearance_without_issued_album_evidence_is_not_displayed(self):
        self.pages.pages['https://www.jimihendrix.com/music/']='<h1>Jimi Hendrix</h1><a href="/music/unproven/">Announced Album</a>'
        result=self.service.search('Jimi Hendrix')
        self.assertEqual(result['status'],'unconfirmed')
        self.assertEqual(result['artist']['albums'],[])
        self.assertIsNone(self.service.cache.get('Jimi Hendrix'))

    def test_future_and_wrong_artist_albums_rejected(self):
        url='https://www.jimihendrix.com/music/'
        for html in [album_json('Other Artist','False Match',url+'false/'),album_json('Jimi Hendrix','Future',url+'future/').replace('2001-01-01','2099-01-01')]:
            self.pages.pages[url]=html
            result=self.service.search('Jimi Hendrix',refresh=True)
            self.assertEqual(result['artist']['albums'],[])
            self.assertEqual(result['status'],'unconfirmed')

    def test_absent_blocked_and_fetch_failure_remain_distinct(self):
        missing=self.service.search('No Such Name')
        self.assertEqual(missing['status'],'not_found')
        self.pages.fail=True
        blocked=self.service.search('Jimi Hendrix')
        self.assertEqual(blocked['status'],'blocked')
        self.assertTrue(all(s['status']=='blocked' for s in blocked['sources']))
        def timeout(source):raise SourceError('fetch_error','timeout')
        self.service.fetch=timeout
        failed=self.service.search('Jimi Hendrix')
        self.assertEqual(failed['status'],'fetch_error')

    def test_partial_failure_keeps_only_proven_works(self):
        self.pages.pages.pop('https://www.milesdavis.com/albums/')
        original=self.service.fetch
        def fetch(source):
            if source['host']=='www.milesdavis.com':raise SourceError('blocked','403')
            return original(source)
        self.service.fetch=fetch
        result=self.service.search('Miles Davis')
        self.assertEqual(result['status'],'partial')
        self.assertEqual([a['title'] for a in result['artist']['albums']],['ドゥー・バップ'])

    def test_failed_refresh_does_not_delete_or_extend_cached_evidence(self):
        first=self.service.search('Norah Jones')
        expiry=first['artist']['albums'][0]['validUntilUnix']
        self.now+=100
        self.pages.fail=True
        result=self.service.search('Norah Jones',refresh=True)
        self.assertTrue(result['cache']['refreshFailed'])
        self.assertEqual(result['artist']['albums'][0]['validUntilUnix'],expiry)
        self.now=expiry+1
        expired=self.service.search('Norah Jones')
        self.assertFalse(expired['cache']['hit'])
        self.assertEqual(expired['artist']['albums'],[])
        self.assertEqual(expired['status'],'blocked')

    def test_invalid_queries_cannot_request_urls(self):
        for query in ['', 'https://evil.test/', 'a'*121,'\x00Artist']:
            with self.assertRaises(ValueError):self.service.search(query)
        self.assertEqual(self.pages.calls,[])

    def test_unapproved_redirect_hosts_rejected_before_network(self):
        transport=OfficialTransport({'www.bluenote.com'},access_policy=type('FixturePolicy',(),{'permits':lambda self,host:True})())
        for url in ['https://www.bluenote.com.evil.test/','http://www.bluenote.com/','https://user@www.bluenote.com/']:
            with self.assertRaises(SourceError):transport({'url':url,'host':'www.bluenote.com'})

    def test_tampered_disk_cache_is_not_trusted(self):
        result=self.service.search('Norah Jones')
        result['artist']['albums'][0]['sourceUrl']='https://evil.test/fake'
        result['artist']['albums'][1]['validUntilUnix']=0
        with self.service.cache.db:
            self.service.cache.db.execute('UPDATE verified SET body=?',(json.dumps(result),))
        self.assertIsNone(self.service.cache.get('Norah Jones'))

    def test_artist_html_requires_release_date_not_article_timestamp(self):
        index_url='https://www.jimihendrix.com/music/'
        detail_url=index_url+'released-album/'
        self.pages.pages[index_url]='<div class="views-field-title-music"><a href="'+detail_url+'">Released Album</a></div>'
        detail='<meta property="og:description" content="Official album on vinyl and CD"><div class="music-artist">Jimi Hendrix</div><h1 class="music-title">Released Album</h1><div class="music-release-date">November 10, 2023</div><time datetime="2000-01-01">Article date</time><section id="music-tracks">Track Listing</section><footer>Experience Hendrix</footer>'
        self.pages.pages[detail_url]=detail
        result=self.service.search('Jimi Hendrix')
        self.assertEqual(result['status'],'confirmed')
        album=result['artist']['albums'][0]
        self.assertEqual(album['generationProof']['listedReleaseDate'],'2023-11-10')
        self.assertEqual(album['sourceUrl'],detail_url)
        self.assertEqual(album['year'],'2023')
        for bad in [detail.replace('November 10, 2023','November 10, 2099'),detail.replace('music-release-date','article-date'),detail.replace('Jimi Hendrix','Other Artist'),detail.replace('Official album on vinyl and CD','Documentary video')]:
            self.pages.pages[detail_url]=bad
            # Clear the old valid proof so failure cannot be hidden by cache reuse.
            with self.service.cache.db:self.service.cache.db.execute('DELETE FROM verified')
            result=self.service.search('Jimi Hendrix',refresh=True)
            self.assertEqual(result['artist']['albums'],[])

    def test_different_works_keep_individual_cache_expiry(self):
        first=self.service.search('Norah Jones')
        old_expiry=first['artist']['albums'][0]['validUntilUnix']
        self.now+=100
        url='https://www.bluenote.com/artist/norah-jones/'
        self.pages.pages[url]=self.pages.pages[url].replace('Come Away With Me','Another Released Album').replace('Feels Like Home','Another Released Album')
        self.service.search('Norah Jones',refresh=True)
        self.now=old_expiry+1
        result=self.service.search('Norah Jones')
        self.assertEqual([a['title'] for a in result['artist']['albums']],['Another Released Album'])

    def test_wsgi_api_and_private_file_paths(self):
        app=create_app(self.service)
        def request(path,query='',method='GET'):
            statuses=[]
            body=b''.join(app({'PATH_INFO':path,'QUERY_STRING':query,'REQUEST_METHOD':method},lambda status,headers:statuses.append(status)))
            return statuses[0],body
        status,body=request('/api/search',urlencode({'q':'ジミ・ヘンドリックス'}))
        self.assertEqual(status,'200 OK')
        self.assertEqual(json.loads(body)['status'],'confirmed')
        self.assertEqual(request('/api/search','q=https%3A%2F%2Fevil.test')[0],'400 Bad Request')
        for path in ['/server/search.py','/data/official-catalog.json','/../cache.sqlite3','/.git/config']:
            self.assertEqual(request(path)[0],'404 Not Found')
        self.assertEqual(request('/api/search','q=A','POST')[0],'405 Method Not Allowed')

if __name__=='__main__':unittest.main()
