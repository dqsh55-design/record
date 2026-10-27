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
        self.review=dict(candidateId=self.report['candidates'][0]['id'],decision='approve',title='Visions',year='2024',label='Blue Note Records',checkedAt='2026-10-26',reviewer='test reviewer',note='Artist, title and label verified on release page')

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
        for patch in [dict(checkedAt='2099-01-01'),dict(checkedAt='2026-02-30'),dict(note=''),dict(reviewer=''),dict(title=''),dict(label='unknown'),dict(decision='pending'),dict(year='not a year')]:
            with self.subTest(patch=patch),self.assertRaises((ValueError,KeyError)):
                m.publish(self.catalog,self.report,[dict(self.review,**patch)],[self.s])

    def test_spoofed_source_rejected(self):
        for url in ['https://www.bluenote.com.evil.test/releases/a/','https://user@www.bluenote.com/releases/a/','http://www.bluenote.com/releases/a/']:
            report=copy.deepcopy(self.report)
            report['candidates'][0]['sourceUrl']=url
            with self.assertRaises(ValueError):m.publish(self.catalog,report,[self.review],[self.s])

if __name__=='__main__':unittest.main()
