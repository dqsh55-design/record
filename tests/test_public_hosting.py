import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
from realtime_fixtures import make_service,fixture_config,Pages
from server.app import create_app
from server.search import OfficialSearch,VerifiedCache,OfficialTransport,SourceError
from scripts.configure_public_api import configure


class PublicHosting(unittest.TestCase):
    def call(self, app, origin=None, query='q=Norah+Jones', method='GET'):
        response={}
        environ=dict(PATH_INFO='/api/search',QUERY_STRING=query,REQUEST_METHOD=method)
        if origin is not None: environ['HTTP_ORIGIN']=origin
        def start(status,headers):response.update(status=status,headers=dict(headers))
        response['body']=json.loads(b''.join(app(environ,start)))
        return response

    def test_pages_cors_allows_exact_origin_only(self):
        service,pages=make_service();self.addCleanup(service.cache.close)
        app=create_app(service,allowed_origins=['https://dqsh55-design.github.io'])
        accepted=self.call(app,'https://dqsh55-design.github.io')
        self.assertEqual(accepted['headers']['Access-Control-Allow-Origin'],'https://dqsh55-design.github.io')
        self.assertNotIn('Access-Control-Allow-Credentials',accepted['headers'])
        before=len(pages.calls)
        for origin in ['null','https://evil.test','https://dqsh55-design.github.io.evil.test']:
            denied=self.call(app,origin)
            self.assertTrue(denied['status'].startswith('403'))
            self.assertNotIn('Access-Control-Allow-Origin',denied['headers'])
        self.assertEqual(len(pages.calls),before)

    def test_rate_limit_rejects_before_search_and_recovers(self):
        service,pages=make_service();self.addCleanup(service.cache.close)
        now=[0];app=create_app(service,request_limit=2,clock=lambda:now[0])
        self.call(app);self.call(app)
        limited=self.call(app)
        self.assertTrue(limited['status'].startswith('429'))
        self.assertEqual(limited['headers']['Retry-After'],'60')
        now[0]=61
        self.assertTrue(self.call(app)['status'].startswith('200'))

    def test_short_refresh_cooldown_and_negative_cache_reduce_fetches(self):
        now=[1793059200];config=fixture_config();config.update(refreshCooldownSeconds=300,negativeCacheSeconds=300)
        pages=Pages();service=OfficialSearch(config,':memory:',fetch=pages,clock=lambda:now[0]);self.addCleanup(service.cache.close)
        first=service.search('Norah Jones');before=len(pages.calls)
        self.assertTrue(service.search('ノラジョーンズ',refresh=True)['cache']['hit'])
        self.assertEqual(len(pages.calls),before)
        now[0]+=301;pages.fail=True
        failed=service.search('Norah Jones',refresh=True)
        self.assertTrue(failed['cache']['refreshFailed'])
        self.assertEqual(failed['artist']['albums'][0]['validUntilUnix'],first['artist']['albums'][0]['validUntilUnix'])
        before=len(pages.calls)
        self.assertTrue(service.search('ノラジョーンズ',refresh=True)['cache']['refreshFailed'])
        self.assertEqual(len(pages.calls),before)
        service.search('Unknown Name');before=len(pages.calls)
        service.search('Unknown Name',refresh=True)
        self.assertEqual(len(pages.calls),before)
        now[0]+=301;service.search('Unknown Name');self.assertGreater(len(pages.calls),before)

    def test_daily_fetch_budget_persists_and_resets_without_proof(self):
        now=[1793059200]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'verified.sqlite3'
            cache=VerifiedCache(path,fixture_config(),clock=lambda:now[0])
            self.assertTrue(cache.reserve_fetch(2));self.assertTrue(cache.reserve_fetch(2));cache.close()
            cache=VerifiedCache(path,fixture_config(),clock=lambda:now[0]);self.addCleanup(cache.close)
            self.assertFalse(cache.reserve_fetch(2))
            self.assertIsNone(cache.get('Norah Jones'))
            now[0]+=86400;self.assertTrue(cache.reserve_fetch(2))

    def test_budget_denial_never_contacts_official_host(self):
        transport=OfficialTransport({'www.bluenote.com'},reserve=lambda:False)
        with patch('server.search.build_opener') as opener:
            with self.assertRaises(SourceError) as error:transport({'host':'www.bluenote.com','url':'https://www.bluenote.com/artists/'})
            self.assertEqual(error.exception.kind,'budget_exhausted');opener.assert_not_called()

    def test_public_configuration_never_accepts_credentials_or_insecure_url(self):
        html='<meta name="record-api-base" content=""><meta name="record-search-mode" content="catalog">'
        self.assertIn('https://api.example.test/',configure(html,'https://api.example.test'))
        self.assertIn('record-search-mode" content="api',configure(html,'https://api.example.test'))
        for base in ['http://api.test','https://secret@api.test','https://api.test/?key=secret','https://api.test/path','https://api.test:443','https://api.test/\"']:
            with self.assertRaises(ValueError):configure(html,base)
        with patch.dict(os.environ,{'RECORD_REQUIRE_DATABASE':'1','RECORD_DATABASE_URL':''}):
            with self.assertRaises(ValueError):create_app()

    def test_directory_aliases_cannot_contaminate_later_artist_search(self):
        service,_=make_service();self.addCleanup(service.cache.close)
        norah=service.search('Norah Jones')
        other=service.search('New Artist')
        self.assertNotIn('New Artist',norah['artist'].get('aliases',[]))
        self.assertFalse(other['cache']['hit'])
        self.assertEqual([a['title'] for a in other['artist']['albums']],['A Newly Discovered Album'])

    def test_no_db_credentials_in_public_error(self):
        service,_=make_service();self.addCleanup(service.cache.close)
        service.search=lambda *args,**kwargs:(_ for _ in ()).throw(RuntimeError('postgres://secret:password@private'))
        response=self.call(create_app(service))
        self.assertTrue(response['status'].startswith('503'))
        self.assertNotIn('password',json.dumps(response))


if __name__=='__main__':unittest.main()
