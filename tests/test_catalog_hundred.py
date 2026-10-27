"""Official listings, unique work additions and unchanged pre-existing catalog."""
import copy
import hashlib
import json
from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
CATALOG=json.loads((ROOT/'data/official-catalog.json').read_text())
FILE='data/official-reviews/catalog-hundred-2026-10-27.json'
REVIEW=json.loads((ROOT/FILE).read_text())
PREFIX='official:hundred-20261027:'

class CatalogHundred(unittest.TestCase):
    def test_twenty_three_records_match_official_listing_reviews(self):
        self.assertEqual(REVIEW['recognitionBasis'],'official-release-listing')
        self.assertEqual(REVIEW['reviewDecision'],'approve')
        added={album['id']:(artist,album) for artist in CATALOG['artists'] for album in artist['albums'] if album['id'].startswith(PREFIX)}
        self.assertEqual(len(added),23)
        self.assertEqual(set(added),{w['catalogId'] for w in REVIEW['works']})
        for work in REVIEW['works']:
            with self.subTest(title=work['title']):
                artist,album=added[work['catalogId']]
                self.assertEqual(artist['id'],work['artistId'])
                self.assertEqual(artist['name'],work['artist'])
                for key in ['title','sourceUrl','sourceName','label']:self.assertEqual(album[key],work[key])
                self.assertEqual(album['year'],work['displayYear'])
                self.assertEqual(album['checkedAt'],REVIEW['checkedAt'])
                self.assertEqual(album['evidenceFile'],FILE)
                self.assertEqual(album['reviewer'],REVIEW['reviewer'])
                self.assertTrue(album['official']);self.assertEqual(album['scope'],'work')
                self.assertTrue(work['officialListingConfirmed']);self.assertEqual(work['listedAs'],'album')
                url=urlsplit(album['sourceUrl']);self.assertEqual(url.scheme,'https')
                self.assertIn(url.netloc,{'www.milesdavis.com','www.bluenote.com','wmg.jp'})
                self.assertRegex(work['sourceSha256'],r'^[a-f0-9]{64}$')
                self.assertNotIn('thumbnail',album)

    def test_all_previous_seventy_seven_entries_are_preserved(self):
        baseline=copy.deepcopy(CATALOG)
        baseline['artists']=baseline['artists'][:5]  # Snapshot of the original five artists.
        for artist in baseline['artists']:artist['albums']=[a for a in artist['albums'] if not a['id'].startswith(PREFIX)]
        self.assertEqual(sum(len(a['albums']) for a in baseline['artists']),77)
        digest=hashlib.sha256(json.dumps(baseline,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(digest,REVIEW['baselineCatalogFingerprint'])

    def test_hundred_works_without_duplicate_ids_titles_or_sources_in_new_batch(self):
        self.assertEqual({a['name']:len(a['albums']) for a in CATALOG['artists'][:5]},{'Norah Jones':13,'Miles Davis':72,'Bill Frisell':9,'Cannonball Adderley':1,'Ambrose Akinmusire':5})
        self.assertEqual(sum(len(a['albums']) for a in CATALOG['artists']),385)
        self.assertEqual(len({w['sourceUrl'] for w in REVIEW['works']}),23)
        for artist in CATALOG['artists']:
            ids=[a['id'] for a in artist['albums']];self.assertEqual(len(ids),len(set(ids)))
            titles=[re.sub(r'[^\w]','',a['title'].casefold()) for a in artist['albums']]
            self.assertEqual(len(titles),len(set(titles)))

    def test_recording_years_and_publisher_history_are_not_inferred(self):
        works={w['title']:w for w in REVIEW['works']}
        self.assertEqual(works['Black Beauty: Miles Davis At Fillmore West']['displayYear'],'1973')
        self.assertEqual(works['Black Beauty: Miles Davis At Fillmore West']['sourceRecordingPeriod'],'Apr 1970')
        self.assertEqual(works['Jazz Track']['label'],'Play Digital')
        self.assertEqual(works['Miles Davis Quintet - Live In Europe 1967: The Bootleg Series Vol. 1']['displayYear'],'2011')
        self.assertTrue(works['Miles Davis Quintet - Live In Europe 1967: The Bootleg Series Vol. 1']['officialListingConfirmed'])
        self.assertEqual(works['In My Dreams']['displayYear'],'2026')
        self.assertEqual(works['THE INTERCONTINENTALS']['catalogNumber'],'WPCR-19071')

    def test_verified_bill_link_is_resolved_canonical_not_a_guessed_id(self):
        bill=CATALOG['artists'][2];album=next(a for a in bill['albums'] if a['title']=='In My Dreams');link=album['listeningLink']
        report=REVIEW['listeningChecks'][0]
        self.assertEqual(link['url'],report['canonicalUrl']);self.assertTrue(report['canonicalRefetched'])
        self.assertNotEqual(report['listedTargetUrl'],report['canonicalUrl'])
        self.assertEqual(link['target']['url'],link['url'])
        self.assertEqual(link['target']['title'],album['title'])
        self.assertEqual(link['target']['type'],'music.album')
        self.assertIn(link['target']['artist'],bill['aliases'])
        self.assertEqual(link['officialSourceUrl'],album['sourceUrl'])
        self.assertFalse(report['playbackVerified'])
        self.assertEqual(sum(bool(a.get('listeningLink')) for artist in CATALOG['artists'] for a in artist['albums']),6)
        # Direct-link availability does not gate approved official release listings.
        self.assertEqual(sum(bool(a.get('listeningLink')) for artist in CATALOG['artists'] for a in artist['albums'] if a['id'].startswith(PREFIX)),1)

if __name__=='__main__':unittest.main()
