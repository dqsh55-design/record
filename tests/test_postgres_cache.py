"""Real PostgreSQL integration; CI provides a disposable TLS-enabled database."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from realtime_fixtures import fixture_config,Pages
from server.search import OfficialSearch,VerifiedCache

URL=os.environ.get('RECORD_TEST_DATABASE_URL')

@unittest.skipUnless(URL,'TLS PostgreSQL integration database not configured locally')
class PostgresCache(unittest.TestCase):
    def setUp(self):
        self.now=1793059200
        self.config=fixture_config()
        self.cache=VerifiedCache(URL,self.config,clock=lambda:self.now)
        self.addCleanup(self.cache.close)
        with self.cache.transaction() as db:
            for table in ['verified','queries','fetch_budget']:db.execute('DELETE FROM '+table)

    def service(self):
        pages=Pages()
        service=OfficialSearch(self.config,URL,fetch=pages,clock=lambda:self.now)
        self.addCleanup(service.cache.close)
        return service,pages

    def test_three_artists_survive_process_restart_without_source_fetch(self):
        service,_=self.service()
        first={name:service.search(name) for name in ['Jimi Hendrix','Norah Jones','Miles Davis']}
        service.cache.close()
        restarted,pages=self.service();pages.fail=True
        for name,body in first.items():
            result=restarted.search(name)
            self.assertTrue(result['cache']['hit'])
            self.assertEqual(result['artist']['albums'],body['artist']['albums'])
        self.assertEqual(pages.calls,[])

    def test_expired_or_tampered_proof_not_displayed(self):
        service,_=self.service();body=service.search('Norah Jones')
        body['artist']['albums'][0]['sourceUrl']='https://evil.test/fake'
        body['artist']['albums'][1]['validUntilUnix']=0
        with self.cache.transaction() as db:db.execute('UPDATE verified SET body=%s',(json.dumps(body),))
        self.assertIsNone(self.cache.get('Norah Jones'))
        self.now+=86401
        self.assertIsNone(self.cache.get('Norah Jones'))

    def test_atomic_budget_shared_between_connections_and_restarts(self):
        # Initialize schema before concurrently opening independent connections.
        self.assertIsNone(self.cache.get('None'))
        caches=[VerifiedCache(URL,self.config,clock=lambda:self.now) for _ in range(4)]
        for cache in caches:self.addCleanup(cache.close)
        with ThreadPoolExecutor(max_workers=4) as pool:
            accepted=list(pool.map(lambda i:caches[i%4].reserve_fetch(7),range(16)))
        self.assertEqual(sum(accepted),7)
        self.assertFalse(VerifiedCache(URL,self.config,clock=lambda:self.now).reserve_fetch(7))
        self.now+=86400
        self.assertTrue(self.cache.reserve_fetch(7))

    def test_unverified_writes_and_plaintext_database_connections_refused(self):
        with self.assertRaises(ValueError):self.cache.save('fake',{'artist':{'id':'fake','albums':[]}})
        with self.assertRaises(ValueError):VerifiedCache('postgresql://localhost/test?sslmode=disable',self.config)

    def test_failed_refresh_does_not_extend_persistent_evidence(self):
        service,pages=self.service();first=service.search('Norah Jones')
        pages.fail=True;self.now+=600
        result=service.search('Norah Jones',refresh=True)
        self.assertTrue(result['cache']['refreshFailed'])
        self.assertEqual(result['artist']['albums'],first['artist']['albums'])
        self.now+=86401
        self.assertIsNone(self.cache.get('Norah Jones'))


if __name__=='__main__':unittest.main()
