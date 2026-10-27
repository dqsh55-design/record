"""Official-release listing is the recognition basis; listening is independent."""
import copy
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
CATALOG=json.loads((ROOT/'data/official-catalog.json').read_text())
FILE='data/official-reviews/miles-discography-2026-10-27.json'
REVIEW=json.loads((ROOT/FILE).read_text())
PREFIX='official:miles-discography-20261027:'

class MilesDiscography(unittest.TestCase):
    def test_twelve_distinct_official_release_listings_match_published_records(self):
        self.assertEqual(REVIEW['recognitionBasis'],'official-release-listing')
        self.assertEqual(REVIEW['reviewDecision'],'approve')
        self.assertEqual(REVIEW['officialIndexUrl'],'https://www.milesdavis.com/music/releases/')
        self.assertRegex(REVIEW['officialIndexSha256'],r'^[a-f0-9]{64}$')
        miles=next(a for a in CATALOG['artists'] if a['id']==REVIEW['artistId'])
        added={a['id']:a for a in miles['albums'] if a['id'].startswith(PREFIX)}
        self.assertEqual(len(added),12)
        self.assertEqual(set(added),{w['catalogId'] for w in REVIEW['works']})
        self.assertEqual(len({w['sourceUrl'] for w in REVIEW['works']}),12)
        for work in REVIEW['works']:
            with self.subTest(work=work['title']):
                album=added[work['catalogId']]
                self.assertTrue(work['officialListingConfirmed'])
                self.assertEqual(work['listedAs'],'album')
                for field in ['title','sourceUrl','sourceName','label']:self.assertEqual(album[field],work[field])
                self.assertTrue(album['sourceUrl'].startswith('https://www.milesdavis.com/albums/'))
                self.assertEqual(album['year'],work['displayYear'])
                self.assertEqual(album['checkedAt'],REVIEW['checkedAt'])
                self.assertEqual(album['evidenceFile'],FILE)
                self.assertEqual(album['reviewer'],REVIEW['reviewer'])
                self.assertTrue(album['official']);self.assertEqual(album['scope'],'work')
                self.assertTrue(album['reviewNote'])
                self.assertRegex(work['sourceSha256'],r'^[a-f0-9]{64}$')
                self.assertNotIn('thumbnail',album)

    def test_all_previous_sixty_five_records_and_artist_metadata_are_preserved(self):
        baseline=copy.deepcopy(CATALOG)
        baseline['artists']=baseline['artists'][:5]  # Snapshot of the original five artists.
        for artist in baseline['artists']:artist['albums']=[a for a in artist['albums'] if not a['id'].startswith((PREFIX,'official:hundred-20261027:'))]
        self.assertEqual(sum(len(a['albums']) for a in baseline['artists']),65)
        actual=hashlib.sha256(json.dumps(baseline,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(actual,REVIEW['baselineCatalogFingerprint'])

    def test_display_dates_do_not_replace_release_year_with_recording_year(self):
        works={w['title']:w for w in REVIEW['works']}
        self.assertEqual(works['Miles In Tokyo']['displayYear'],'1969')
        self.assertEqual(works['Miles In Tokyo']['sourceRecordingPeriod'],'Jul 1964')
        self.assertEqual(works['Walkin\'']['displayYear'],'1957')
        self.assertEqual(works['Walkin\'']['releaseDatePrecision'],'year')
        self.assertEqual(works['Birth Of The Cool']['label'],'Blue Note (BLU)')
        for work in works.values():
            self.assertIn(work['displayYear'],work['sourceReleaseDate'])
            self.assertLess(int(work['displayYear']),date.today().year)

    def test_confirmed_listening_target_is_independent_of_release_recognition(self):
        miles=CATALOG['artists'][1]
        birth=next(a for a in miles['albums'] if a['id']==PREFIX+'birth-of-the-cool')
        link=birth['listeningLink']
        self.assertEqual(link['artistId'],miles['id']);self.assertEqual(link['albumId'],birth['id'])
        self.assertEqual(link['officialSourceUrl'],birth['sourceUrl'])
        self.assertEqual(link['url'],link['target']['url'])
        self.assertEqual(link['target']['title'],birth['title'])
        self.assertEqual(link['target']['type'],'music.album')
        self.assertIn(link['target']['artist'],miles['aliases'])
        self.assertEqual(sum(bool(a.get('listeningLink')) for a in miles['albums']),1)
        quiet=next(a for a in miles['albums'] if a['id']==PREFIX+'quiet-nights')
        self.assertTrue(quiet['official']);self.assertNotIn('listeningLink',quiet)
        self.assertEqual(REVIEW['listeningChecks'][1]['status'],'fetch_error')
        self.assertFalse(REVIEW['listeningChecks'][0]['playbackVerified'])

    def test_no_duplicate_titles_sources_or_ids(self):
        self.assertEqual(sum(len(a['albums']) for a in CATALOG['artists']),118)
        self.assertEqual(len(CATALOG['artists'][1]['albums']),72)
        for artist in CATALOG['artists']:
            self.assertEqual(len(artist['albums']),len({a['id'] for a in artist['albums']}))
            titles=[re.sub(r'[^\w]','',a['title'].casefold()) for a in artist['albums']]
            self.assertEqual(len(titles),len(set(titles)))

if __name__=='__main__':unittest.main()
