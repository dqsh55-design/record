"""Release listing provenance, additive-only change and independent listening checks."""
import copy
import hashlib
import json
from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]
CATALOG=json.loads((ROOT/'data/official-catalog.json').read_text())
# This historical review covers the original fourteen artists; v0.87 additions are tested separately.
CATALOG['artists']=CATALOG['artists'][:14]
FILE='data/official-reviews/deeper-discographies-2026-10-27.json'
REVIEW=json.loads((ROOT/FILE).read_text())
PREFIX='official:depth-20261027:'
COUNTS={'Norah Jones':13,'Miles Davis':72,'Bill Frisell':9,'Cannonball Adderley':1,'Ambrose Akinmusire':5,'The Beatles':26,'Led Zeppelin':14,'Black Sabbath':7,'Metallica':15,'Kraftwerk':9,'Daft Punk':6,'David Bowie':7,'Michael Jackson':9,'Ryuichi Sakamoto':6}
class DeeperDiscographies(unittest.TestCase):
    def test_existing_118_entries_and_all_artist_fields_unchanged(self):
        old=copy.deepcopy(CATALOG)
        for artist in old['artists']:artist['albums']=[a for a in artist['albums'] if not a['id'].startswith(PREFIX)]
        self.assertEqual(sum(len(a['albums']) for a in old['artists']),118)
        self.assertEqual({a['id'] for artist in old['artists'] for a in artist['albums']},set(REVIEW['baselineAlbumIds']))
        digest=hashlib.sha256(json.dumps(old,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(digest,REVIEW['baselineCatalogFingerprint'])

    def test_81_additions_have_bound_official_listing_reviews(self):
        self.assertEqual(REVIEW['recognitionBasis'],'official-release-listing')
        self.assertEqual(REVIEW['reviewDecision'],'approve')
        added={a['id']:(artist,a) for artist in CATALOG['artists'] for a in artist['albums'] if a['id'].startswith(PREFIX)}
        self.assertEqual(len(added),81)
        self.assertEqual(set(added),{w['catalogId'] for w in REVIEW['works']})
        for work in REVIEW['works']:
            with self.subTest(title=work['title']):
                artist,album=added[work['catalogId']]
                self.assertEqual(artist['id'],work['artistId']);self.assertEqual(artist['name'],work['artist'])
                for key in ['title','label','sourceName','sourceUrl']:self.assertEqual(album[key],work[key])
                self.assertEqual(album['year'],work['displayYear'])
                self.assertEqual(album['evidenceFile'],FILE);self.assertEqual(album['checkedAt'],REVIEW['checkedAt'])
                self.assertEqual(album['reviewer'],REVIEW['reviewer']);self.assertTrue(album['reviewNote'])
                self.assertTrue(album['official']);self.assertEqual(album['scope'],'work')
                self.assertTrue(work['officialListingConfirmed']);self.assertEqual(work['listedAs'],'album')
                url=urlsplit(album['sourceUrl']);self.assertEqual(url.scheme,'https')
                self.assertIn(url.hostname,{'www.thebeatles.com','discography.ledzeppelin.com','www.metallica.com','wmg.jp','www.daftpunk.com','www.commmons.com','www.sonymusic.co.jp'})
                if work['retrievalMethod']=='public-https-html':self.assertRegex(work['sourceSha256'],r'^[a-f0-9]{64}$')
                else:
                    self.assertEqual(work['artist'],'Michael Jackson')
                    self.assertNotIn('sourceSha256',work)
                    self.assertEqual(work['sourceObservationSha256'],hashlib.sha256(work['sourceObservation'].encode()).hexdigest())
                self.assertNotIn('thumbnail',album)

    def test_counts_and_non_duplicate_work_selection(self):
        self.assertEqual({a['name']:len(a['albums']) for a in CATALOG['artists']},COUNTS)
        self.assertEqual(sum(COUNTS.values()),199)
        self.assertEqual(len(REVIEW['works']),len({w['catalogId'] for w in REVIEW['works']}))
        for artist in CATALOG['artists']:
            keys=[re.sub(r'[^\w]','',a['title'].casefold()) for a in artist['albums']]
            self.assertEqual(len(keys),len(set(keys)))
        # Country variants of a compilation and existing Paranoid are held, not padded into the count.
        held=REVIEW['excludedCandidates']
        self.assertTrue(any(w['artist']=='Black Sabbath' and 'ULTIMATE' in w['title'] for w in held))
        self.assertTrue(any(w['artist']=='Metallica' and 'E.P.' in w['title'] for w in held))
        self.assertTrue(any(w['artist']=='Led Zeppelin' and 'DVD' in w['title'] for w in held))
        self.assertNotIn("B’z",[a['name'] for a in CATALOG['artists']])

    def test_recording_years_reissue_years_and_mixed_media_are_explicit(self):
        works={w['title']:w for w in REVIEW['works']}
        self.assertEqual(works['Alive 1997']['displayYear'],'2001')
        self.assertEqual(works['Alive 1997']['sourceReleaseDate'],'2001-10-01')
        self.assertEqual(works['Ryuichi Sakamoto: Playing the Piano 12122020']['displayYear'],'2021')
        self.assertEqual(works['Ryuichi Sakamoto: Playing the Piano 12122020']['sourceReleaseDate'],'2021-12-12')
        self.assertEqual(works['放射能（ラジオ-アクティヴィティ）']['displayYear'],'1975')
        self.assertEqual(works['放射能（ラジオ-アクティヴィティ）']['sourceReleaseDate'],'2024-06-26')
        self.assertEqual(works['Stage 2017（ステージ 2017ミックス）']['displayYear'],'2018')
        path=next(w for w in REVIEW['works'] if w['title'].startswith('path_'))
        self.assertIn('CD album',path['packageFormat']);self.assertTrue(path['supplementarySourceUrl'])
        self.assertTrue(any('403' in failure['error'] for failure in REVIEW['retrievalFailures']))

    def test_two_new_direct_links_and_a_single_display_mismatch_stay_separate_from_release_recognition(self):
        new=[(artist,a) for artist in CATALOG['artists'] for a in artist['albums'] if a['id'].startswith(PREFIX) and a.get('listeningLink')]
        self.assertEqual({a['title'] for _,a in new},{'Human After All','Alive 2007'})
        checks={r.get('catalogId'):r for r in REVIEW['listeningChecks'] if r['decision']=='direct'}
        for artist,album in new:
            link=album['listeningLink'];check=checks[album['id']]
            self.assertEqual(link['artistId'],artist['id']);self.assertEqual(link['albumId'],album['id'])
            self.assertEqual(link['target']['artist'],artist['name']);self.assertEqual(link['target']['title'],album['title'])
            self.assertEqual(link['target']['type'],'music.album')
            self.assertEqual(link['url'],link['target']['url']);self.assertEqual(link['url'],check['canonicalUrl'])
            self.assertIn(link['url'],check['listedTargetUrl'])
            self.assertEqual(link['officialSourceUrl'],album['sourceUrl'])
            self.assertFalse(check['playbackVerified'])
            for field in ['sourceSha256','linkPageSha256','targetSha256']:self.assertRegex(link[field],r'^[a-f0-9]{64}$')
        daft=next(a for a in CATALOG['artists'] if a['name']=='Daft Punk')
        alive=next(a for a in daft['albums'] if a['title']=='Alive 1997')
        self.assertTrue(alive['official']);self.assertNotIn('listeningLink',alive)
        mismatch=next(c for c in REVIEW['listeningChecks'] if c['title']=='Alive 1997')
        self.assertEqual(mismatch['decision'],'search');self.assertEqual(mismatch['targetDescription'],'シングル • Daft Punk')
        self.assertEqual(sum(bool(a.get('listeningLink')) for artist in CATALOG['artists'] for a in artist['albums']),6)
if __name__=='__main__':unittest.main()
