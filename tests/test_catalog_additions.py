"""Official review, additive-only catalog change and release-date precision."""
import copy
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
CATALOG=json.loads((ROOT/'data/official-catalog.json').read_text())
EVIDENCE='data/official-reviews/catalog-expansion-2026-10-27.json'
REVIEW=json.loads((ROOT/EVIDENCE).read_text())
PREFIX='official:expansion-20261027:'

class CatalogAdditions(unittest.TestCase):
    def test_all_nine_additions_have_matching_approved_official_release_evidence(self):
        self.assertEqual(REVIEW['reviewDecision'],'approve')
        self.assertEqual(REVIEW['reviewScope'],'work')
        self.assertFalse(REVIEW['automatedCollection'])
        added={a['id']:(artist,a) for artist in CATALOG['artists'] for a in artist['albums'] if a['id'].startswith(PREFIX)}
        self.assertEqual(len(added),9)
        self.assertEqual(set(added),{w['catalogId'] for w in REVIEW['works']})
        for work in REVIEW['works']:
            with self.subTest(work=work['title']):
                artist,album=added[work['catalogId']]
                self.assertEqual(artist['id'],work['artistId'])
                self.assertEqual(artist['name'],work['artist'])
                for key in ['title','sourceUrl','sourceName','label']:self.assertEqual(album[key],work[key])
                self.assertEqual(album['year'],work['displayYear'])
                self.assertEqual(album['checkedAt'],REVIEW['checkedAt'])
                self.assertEqual(album['reviewer'],REVIEW['reviewer'])
                self.assertEqual(album['evidenceFile'],EVIDENCE)
                self.assertTrue(album['official']);self.assertEqual(album['scope'],'work')
                self.assertTrue(album['reviewNote'])
                self.assertRegex(work['sourceSha256'],r'^[0-9a-f]{64}$')
                url=urlsplit(album['sourceUrl']);self.assertEqual(url.scheme,'https')
                self.assertIn(url.netloc,{'www.milesdavis.com','www.universal-music.co.jp'})
                self.assertIn(work['medium'],{'audio-album','CD'})
                self.assertIn(album['year'],work['sourceReleaseDate'])
                self.assertLess(int(album['year']),date.today().year)
                self.assertNotIn('listeningLink',album)
                self.assertNotIn('thumbnail',album)

    def test_all_previously_published_entries_and_listening_evidence_are_unchanged(self):
        baseline=copy.deepcopy(CATALOG)
        for artist in baseline['artists']:artist['albums']=[a for a in artist['albums'] if not a['id'].startswith((PREFIX,'official:miles-discography-20261027:','official:hundred-20261027:'))]
        self.assertEqual(sum(len(a['albums']) for a in baseline['artists']),56)
        fingerprint=hashlib.sha256(json.dumps(baseline,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(fingerprint,REVIEW['baselineCatalogFingerprint'])

    def test_release_dates_are_not_confused_with_recording_or_reissue_dates(self):
        works={w['title']:w for w in REVIEW['works']}
        for title,year in [('Dark Magus','1977'),('The Man With The Horn','1981'),('We Want Miles','1982'),('Star People','1983'),('Decoy','1984'),('You’re Under Arrest','1985')]:
            self.assertEqual(works[title]['displayYear'],year)
        self.assertEqual(works['Dark Magus']['sourceReleaseDate'],'1977')
        self.assertEqual(works['Dark Magus']['releaseDatePrecision'],'year')
        covers=works['Covers（カヴァーズ〜私のお気に入り）']
        self.assertEqual(covers['sourceReleaseDate'],'2012-10-31')
        self.assertEqual(covers['sourceOriginalReleaseDate'],'2012.05.15')
        self.assertEqual(covers['catalogNumber'],'TOCP-71410')

    def test_supported_counts_no_duplicate_work_ids_titles_or_held_candidates(self):
        counts={a['name']:len(a['albums']) for a in CATALOG['artists']}
        self.assertEqual(counts['Norah Jones'],13);self.assertEqual(counts['Miles Davis'],72)
        self.assertEqual(sum(counts.values()),100)
        for artist in CATALOG['artists']:
            self.assertEqual(len(artist['albums']),len({a['id'] for a in artist['albums']}))
            keys=[re.sub(r'[^\w]','',a['title'].casefold()) for a in artist['albums']]
            self.assertEqual(len(keys),len(set(keys)))
        approved={w['sourceUrl'] for w in REVIEW['works']}
        for held in REVIEW['heldCandidates']:self.assertNotIn(held['sourceUrl'],approved)

if __name__=='__main__':unittest.main()
