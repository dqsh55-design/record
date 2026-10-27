"""Regression contract for individually reviewed Columbia works."""
import copy
import hashlib
import json
from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
CATALOG=json.loads((ROOT/'data/official-catalog.json').read_text())
REVIEW=json.loads((ROOT/'data/official-reviews/miles-columbia-2026-10-27.json').read_text())

class ColumbiaCatalogTests(unittest.TestCase):
    def test_every_added_work_has_matching_approved_official_evidence(self):
        self.assertEqual(REVIEW['reviewDecision'],'approve')
        self.assertEqual(REVIEW['reviewScope'],'work')
        self.assertFalse(REVIEW['automatedCollection'])
        miles=next(a for a in CATALOG['artists'] if a['id']==REVIEW['artistId'])
        added={a['id']:a for a in miles['albums'] if a['id'].startswith('official:miles-columbia:')}
        self.assertEqual(len(added),18)
        self.assertEqual(set(added),{w['catalogId'] for w in REVIEW['works']})
        self.assertEqual(len({w['sourceUrl'] for w in REVIEW['works']}),18)
        for work in REVIEW['works']:
            with self.subTest(title=work['title']):
                album=added[work['catalogId']]
                for field in ['title','sourceUrl','label','sourceName']:
                    self.assertEqual(album[field],work[field])
                self.assertEqual(album['year'],work['displayYear'])
                self.assertTrue(album['official'])
                self.assertEqual(album['scope'],'work')
                self.assertEqual(album['label'],'Columbia Records')
                self.assertEqual(album['checkedAt'],REVIEW['checkedAt'])
                self.assertTrue(album['reviewNote'].strip())
                self.assertTrue(album['reviewer'].strip())
                self.assertEqual(album['evidenceFile'],'data/official-reviews/miles-columbia-2026-10-27.json')
                url=urlsplit(work['sourceUrl'])
                self.assertEqual(url.scheme,'https')
                self.assertEqual(url.netloc,'www.milesdavis.com')
                self.assertRegex(url.path,r'^/albums/[^/]+/$')
                self.assertTrue(work['sourceReleaseDate'])
                self.assertTrue(work['sourceRecordingPeriod'])
                if 'sonyJapanReissue' in work:
                    self.assertFalse(work['sonyJapanReissue']['yearUsedAsOriginal'])
                    self.assertEqual(urlsplit(work['sonyJapanReissue']['sourceUrl']).netloc,'www.sonymusic.co.jp')

    def test_existing_twenty_entries_and_artist_metadata_are_unchanged(self):
        baseline=copy.deepcopy(CATALOG)
        baseline['artists']=[a for a in baseline['artists'] if a['id'] in {'985c709c-7771-4de3-9024-7bda29ebe3f9','561d854a-6a28-4aa7-8c99-323e6ce46c2a'}]
        for artist in baseline['artists']:
            artist['albums']=[a for a in artist['albums'] if not a['id'].startswith(('official:miles-columbia:','generated:'))]
        self.assertEqual([len(a['albums']) for a in baseline['artists']],[12,8])
        fingerprint=hashlib.sha256(json.dumps(baseline,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(fingerprint,REVIEW['baselineCatalogFingerprint'])

    def test_recording_reissue_and_uncertain_years_are_not_promoted(self):
        albums={a['title']:a for artist in CATALOG['artists'] for a in artist['albums']}
        for title,year in [('Miles Smiles','1967'),('Nefertiti','1968'),('My Funny Valentine: Miles Davis In Concert','1965'),('‘Four’ & More','1966')]:
            self.assertEqual(albums[title]['year'],year)
        for title in ['Pangaea','Filles De Kilimanjaro','TUTU','Doo-Bop','Begin Again']:
            self.assertIsNone(albums[title]['year'])
        self.assertFalse(any(a.get('year')=='2006' for a in albums.values()))

    def test_blocked_sources_remain_disabled_and_no_duplicates(self):
        sources=json.loads((ROOT/'data/official-sources.json').read_text())['sources']
        for identity in ['miles-davis','miles-sony-japan']:
            self.assertFalse(next(s for s in sources if s['id']==identity)['enabled'])
        for artist in CATALOG['artists']:
            titles=[re.sub(r'[^\w]','',a['title'].casefold()) for a in artist['albums']]
            self.assertEqual(len(titles),len(set(titles)))

if __name__=='__main__':unittest.main()
