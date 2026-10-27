import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('discography', Path(__file__).resolve().parents[1]/'scripts/official_discography.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class DiscographyTests(unittest.TestCase):
    def setUp(self):
        self.s = dict(id='norah',artistId='a',host='www.bluenote.com',url='https://www.bluenote.com/artist/norah-jones/',releasePath=r'/releases/[^/]+/?',name='Blue Note',label='Blue Note')
        self.html = '<a href="/releases/visions/"><span>Visions</span></a><a href="https://evil.test/releases/fake/">Fake</a><a href="/news/">News</a><a href="/releases/visions/">Visions</a>'
        self.report=m.collect([self.s],{},lambda s:self.html)
        self.catalog={'version':1,'artists':[{'id':'a','albums':[]}]}
        self.review=dict(sourceSha256=self.report['sources'][0]['sha256'],candidateTitle='Visions',candidateId=self.report['candidates'][0]['id'],decision='approve',title='Visions',year='2024',label='Blue Note Records',checkedAt='2026-10-26',reviewer='test reviewer',note='Artist, title and label verified on release page')

    def test_bluenote_artist_cards_exclude_band_and_news(self):
        source=dict(self.s,adapter='bluenote-artist',artistName='Norah Jones')
        html='<div class="release-entry"><h5 class="post-name"><strong>Visions - <a>Norah Jones</a></strong></h5></div><div class="release-entry"><h5 class="post-name">Band Album - The Little Willies - Norah Jones</h5></div><h5 class="post-name">News - Norah Jones</h5>'
        candidates=m.extract(source,html)
        self.assertEqual([c['title'] for c in candidates],['Visions'])
        self.assertEqual(candidates[0]['sourceUrl'],source['url'])

    def test_only_release_links_and_stable_ids(self):
        self.assertEqual(len(self.report['candidates']),1)
        self.assertEqual(self.report['candidates'][0]['status'],'pending')
        self.assertEqual(m.extract(self.s,self.html)[0]['id'],self.review['candidateId'])

    def test_failure_retains_candidates_without_publishing(self):
        report=m.collect([self.s],self.report,lambda s:'<html>Changed layout</html>')
        self.assertEqual(report['sources'][0]['status'],'error')
        self.assertEqual(report['candidates'],self.report['candidates'])
        with self.assertRaises(ValueError):m.publish(self.catalog,report,[self.review],[self.s])

    def test_reviewed_addition_is_idempotent_and_original_unchanged(self):
        out=m.publish(self.catalog,self.report,[self.review],[self.s])
        self.assertEqual(len(out['artists'][0]['albums']),1)
        self.assertEqual(out['artists'][0]['albums'][0]['label'],'Blue Note Records')
        self.assertEqual(self.catalog['artists'][0]['albums'],[])
        self.assertEqual(m.publish(out,self.report,[self.review],[self.s]),out)

    def test_missing_review_and_rejection_do_not_publish(self):
        self.assertEqual(m.publish(self.catalog,self.report,[],[self.s]),self.catalog)
        self.review['decision']='reject'
        self.assertEqual(m.publish(self.catalog,self.report,[self.review],[self.s]),self.catalog)

    def test_bad_evidence_aborts_batch(self):
        for patch in [dict(checkedAt='2099-01-01'),dict(checkedAt='2026-02-30'),dict(note=''),dict(reviewer=''),dict(title=''),dict(label='unknown'),dict(decision='pending'),dict(year='not a year'),dict(sourceSha256='wrong'),dict(candidateTitle='Different album')]:
            with self.subTest(patch=patch),self.assertRaises((ValueError,KeyError)):
                m.publish(self.catalog,self.report,[dict(self.review,**patch)],[self.s])

    def test_spoofed_source_rejected(self):
        for url in ['https://www.bluenote.com.evil.test/releases/a/','https://user@www.bluenote.com/releases/a/','http://www.bluenote.com/releases/a/']:
            report=copy.deepcopy(self.report)
            report['candidates'][0]['sourceUrl']=url
            with self.assertRaises(ValueError):m.publish(self.catalog,report,[self.review],[self.s])

    def test_disabled_sources_are_never_requested(self):
        def forbidden(source):
            self.fail('disabled source was requested')
        source=dict(self.s,enabled=False,disabledReason='403; use a different official source')
        report=m.collect([source],{},forbidden)
        self.assertEqual(report['sources'][0]['status'],'disabled')
        self.assertEqual(report['candidates'],[])
        with self.assertRaises(ValueError):
            m.publish(self.catalog,self.report,[self.review],[source])

    def test_warner_only_album_cards_on_matching_artist_path(self):
        source=dict(self.s,adapter='warner-cards',host='wmg.jp',url='https://wmg.jp/miles-davis/discography',releasePath=r'/miles-davis/discography/\d+/?')
        html='<a href="/miles-davis/discography/18010"><h3>ドゥー・バップ&lt;SHM-CD&gt;</h3><span>ALBUM</span><p>2017.05.24 発売</p></a><a href="/miles-davis/discography/18010">Read more</a><a href="/miles-davis/discography/9"><h3>Video</h3><span>映像</span></a><a href="/other/discography/1"><h3>Other</h3><span>ALBUM</span></a>'
        candidates=m.extract(source,html)
        self.assertEqual(len(candidates),1)
        self.assertEqual(candidates[0]['title'],'ドゥー・バップ<SHM-CD>')
        self.assertEqual(candidates[0]['sourceUrl'],'https://wmg.jp/miles-davis/discography/18010')

    def test_later_invalid_review_cannot_partially_mutate_catalog(self):
        other=dict(self.review,candidateId='missing')
        before=copy.deepcopy(self.catalog)
        with self.assertRaises(KeyError):
            m.publish(self.catalog,self.report,[self.review,other],[self.s])
        self.assertEqual(self.catalog,before)

class ObservedCatalogIntegrationTests(unittest.TestCase):
    root = Path(__file__).resolve().parents[1]

    def setUp(self):
        import json
        self.read=lambda p:json.loads((self.root/p).read_text())
        self.sources=self.read('data/official-sources.json')['sources']
        self.report=self.read('tests/fixtures/official-observations.json')
        self.reviews=self.read('data/official-reviews/norah-2026-10-27.json')
        self.catalog=self.read('data/official-catalog.json')

    def test_reduced_real_source_cards_reproduce_all_candidate_ids(self):
        for source_id,fixture,count in [('norah-jones','norah-release-cards.html',12),('miles-warner-japan','warner-release-cards.html',12)]:
            with self.subTest(source=source_id):
                source=next(s for s in self.sources if s['id']==source_id)
                actual=m.extract(source,(self.root/'tests/fixtures'/fixture).read_text())
                expected=[c for c in self.report['candidates'] if c['sourceId']==source_id]
                self.assertEqual(len(actual),count)
                self.assertEqual(actual,expected)

    def test_norah_existing_twelve_preserve_every_field(self):
        self.assertEqual(len(self.reviews),12)
        self.assertEqual(m.publish(self.catalog,self.report,self.reviews,self.sources),self.catalog)

    def test_norah_cli_registers_twelve_then_no_duplicates(self):
        import json,subprocess,sys,tempfile
        blank=copy.deepcopy(self.catalog)
        blank['artists'][0]['albums']=[]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'catalog.json'
            m.write_json(path,blank)
            command=[sys.executable,str(self.root/'scripts/official_discography.py'),'publish','--catalog',str(path),'--report',str(self.root/'tests/fixtures/official-observations.json'),'--sources',str(self.root/'data/official-sources.json'),'--reviews',str(self.root/'data/official-reviews/norah-2026-10-27.json')]
            subprocess.run(command,check=True,capture_output=True,text=True)
            first=path.read_text()
            out=json.loads(first)['artists'][0]['albums']
            self.assertEqual({m.key(a['title']) for a in out},{m.key(a['title']) for a in self.catalog['artists'][0]['albums']})
            self.assertEqual(len(out),12)
            self.assertEqual(next(a for a in out if a['title']=='Not Too Late')['year'],'2007')
            self.assertIsNone(next(a for a in out if a['title']=='Begin Again')['year'])
            self.assertTrue(all(a['official'] and a['scope']=='work' and a['sourceSha256'] for a in out))
            subprocess.run(command,check=True,capture_output=True,text=True)
            self.assertEqual(path.read_text(),first)
            bad=self.reviews+[dict(self.reviews[0],candidateId='invalid')]
            bad_path=Path(directory)/'bad.json'
            m.write_json(bad_path,bad)
            command[-1]=str(bad_path)
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(path.read_text(),first)

    def test_warner_reviewed_works_not_reissue_years(self):
        reviews=self.read('data/official-reviews/miles-warner-2026-10-27.json')
        blank=copy.deepcopy(self.catalog)
        blank['artists'][1]['albums']=[]
        out=m.publish(blank,self.report,reviews,self.sources)['artists'][1]['albums']
        self.assertEqual({a['title'] for a in out},{'TUTU','Doo-Bop'})
        self.assertTrue(all(a['year'] is None and a['sourceUrl'].startswith('https://wmg.jp/miles-davis/discography/') for a in out))
        self.assertEqual(m.publish(self.catalog,self.report,reviews,self.sources),self.catalog)

if __name__=='__main__':unittest.main()
