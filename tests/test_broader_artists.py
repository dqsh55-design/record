"""v0.88 official evidence, prior catalog preservation and listening independence."""
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
FILE='data/official-reviews/broader-artists-v088-2026-10-27.json'
REVIEW=json.loads((ROOT/FILE).read_text())
COUNTS={'Chick Corea':22,'Deep Purple':9,'Megadeth':11,'The Chemical Brothers':10,'New Order':10,'Taylor Swift':17,'椎名林檎':14}
class BroaderArtists(unittest.TestCase):
    def test_complete_previous_292_works_and_artist_metadata_are_unchanged(self):
        old=copy.deepcopy(CATALOG)
        old['artists']=[a for a in old['artists'] if a['id'] in REVIEW['baselineArtistIds']]
        self.assertEqual(len(old['artists']),20)
        self.assertEqual(sum(len(a['albums']) for a in old['artists']),292)
        digest=hashlib.sha256(json.dumps(old,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(digest,REVIEW['baselineCatalogFingerprint'])
        self.assertEqual(sum(bool(a.get('listeningLink')) for art in old['artists'] for a in art['albums']),6)

    def test_all_93_works_have_bound_dated_official_product_evidence(self):
        new=CATALOG['artists'][20:];self.assertEqual({a['name']:len(a['albums']) for a in new},COUNTS)
        self.assertEqual(REVIEW['counts'],COUNTS);self.assertEqual(REVIEW['addedCount'],93)
        self.assertEqual(len(CATALOG['artists']),27);self.assertEqual(sum(len(a['albums']) for a in CATALOG['artists']),385)
        self.assertEqual(REVIEW['recognitionBasis'],'official-release-listing');self.assertEqual(REVIEW['reviewDecision'],'approve')
        evidence={w['catalogId']:w for w in REVIEW['works']};self.assertEqual(len(evidence),93)
        self.assertEqual(len({w['sourceUrl'] for w in evidence.values()}),93)
        for artist in new:
            self.assertTrue(artist['aliases'])
            for album in artist['albums']:
                with self.subTest(title=album['title']):
                    w=evidence[album['id']]
                    for key in ['title','label','sourceUrl','sourceName']:self.assertEqual(album[key],w[key])
                    self.assertEqual(w['artistId'],artist['id']);self.assertEqual(w['artist'],artist['name'])
                    self.assertEqual(w['displayYear'],album['year']);self.assertEqual(album['checkedAt'],REVIEW['checkedAt'])
                    self.assertEqual(album['reviewer'],REVIEW['reviewer']);self.assertEqual(album['evidenceFile'],FILE)
                    self.assertTrue(album['official']);self.assertEqual(album['scope'],'work');self.assertTrue(album['reviewNote'])
                    self.assertTrue(w['officialListingConfirmed']);self.assertEqual(w['listedAs'],'album')
                    self.assertRegex(w['sourceSha256'],r'^[a-f0-9]{64}$');self.assertTrue(w['sourceListingTitle']);self.assertTrue(w['sourceArtistCredit'])
                    self.assertLessEqual(date.fromisoformat(w['sourceReleaseDate']),date.fromisoformat(REVIEW['checkedAt']))
                    url=urlsplit(w['sourceUrl']);self.assertEqual(url.scheme,'https')
                    self.assertIn(url.netloc,{'www.universal-music.co.jp','wmg.jp'})
                    self.assertRegex(url.path,r'/(products/[^/]+/|discography/\d+)$')
                    self.assertNotIn('thumbnail',album);self.assertNotIn('listeningLink',album)

    def test_duplicate_specifications_and_different_artists_are_not_inflated(self):
        albums=[a for art in CATALOG['artists'][20:] for a in art['albums']]
        for art in CATALOG['artists']:
            keys=[re.sub(r'[^\w]','',a['title'].casefold()) for a in art['albums']]
            self.assertEqual(len(keys),len(set(keys)))
        titles=[a['title'] for a in albums]
        for excluded in ['アダムとイヴの林檎','幸福論','サタデーナイト・ゴシップ','MoRA CD-BOX','パリ・コンサート','第7銀河の讃歌']:
            self.assertNotIn(excluded,titles)
        self.assertFalse(any('ジョイ・ディヴィジョン' in t for t in titles))
        self.assertFalse(any(a['name'].casefold() in ["b’z","b'z",'ビーズ'] for a in CATALOG['artists']))
        self.assertTrue(REVIEW['excludedCandidates'])
        credits=[w['sourceArtistCredit'] for w in REVIEW['works'] if w['artist']=='Chick Corea']
        self.assertTrue(all('チック・コリア' in c or 'Chick Corea' in c for c in credits))

    def test_work_years_and_reissue_years_are_distinguished(self):
        bycode={w['sourceUrl'].rstrip('/').split('/')[-1]:w for w in REVIEW['works']}
        self.assertEqual(bycode['32504']['displayYear'],'1972');self.assertEqual(bycode['32504']['sourceReleaseDate'],'2026-03-04')
        self.assertEqual(bycode['29413']['displayYear'],'1983');self.assertEqual(bycode['29413']['sourceReleaseDate'],'2024-07-24')
        self.assertEqual(bycode['uicy-16490']['displayYear'],'1995');self.assertEqual(bycode['uicy-16490']['sourceReleaseDate'],'2026-06-24')
        self.assertEqual(bycode['uccu-46177']['displayYear'],'2026') # Its 1971 recording date is not release evidence.
        taylor=next(a for a in CATALOG['artists'] if a['name']=='Taylor Swift')
        self.assertTrue(any(a['title']=='1989' for a in taylor['albums']))
        self.assertTrue(any(a['title']=='1989（テイラーズ・ヴァージョン）' for a in taylor['albums']))

    def test_unspecified_label_uses_explicit_official_publisher_without_guessing(self):
        for w in REVIEW['works']:
            if w['sourceLabelField'] in ['-','OTHER','Third Party Label']:
                self.assertEqual(w['label'],'Universal Music Japan（発売元）')
            else:self.assertEqual(w['label'],w['sourceLabelField'])

    def test_unverified_listening_and_retrieval_failure_are_separate_from_release(self):
        self.assertTrue(REVIEW['listeningChecks'])
        self.assertTrue(all(w['decision']=='search' for w in REVIEW['listeningChecks']))
        self.assertEqual(sum(bool(a.get('listeningLink')) for art in CATALOG['artists'] for a in art['albums']),6)
        failures=REVIEW['retrievalFailures'];self.assertTrue(any('403' in w['error'] for w in failures))
        self.assertTrue(all(w['usedAsReleaseEvidence'] is False for w in failures))
        self.assertFalse({w['sourceUrl'] for w in failures}&{w['sourceUrl'] for w in REVIEW['works']})
if __name__=='__main__':unittest.main()
