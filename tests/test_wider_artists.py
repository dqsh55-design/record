"""Official release evidence across six genres, with the old catalog held intact."""
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
# Historical v0.87 review; later additions have their own complete-baseline test.
CATALOG['artists']=CATALOG['artists'][:20]
FILE='data/official-reviews/wider-artists-v087-2026-10-27.json'
REVIEW=json.loads((ROOT/FILE).read_text())
COUNTS={'John Coltrane':29,'Queen':17,'Iron Maiden':22,'Underworld':6,'Madonna':10,'宇多田ヒカル':9}
class WiderArtists(unittest.TestCase):
    def test_previous_199_works_artist_fields_and_six_direct_links_are_unchanged(self):
        old=copy.deepcopy(CATALOG)
        old['artists']=[a for a in old['artists'] if a['id'] in REVIEW['baselineArtistIds']]
        self.assertEqual(len(old['artists']),14)
        self.assertEqual(sum(len(a['albums']) for a in old['artists']),199)
        digest=hashlib.sha256(json.dumps(old,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(digest,REVIEW['baselineCatalogFingerprint'])
        self.assertEqual(sum(bool(a.get('listeningLink')) for artist in old['artists'] for a in artist['albums']),6)

    def test_six_genres_93_matching_official_reviews_and_no_uniform_count_cap(self):
        self.assertEqual(REVIEW['recognitionBasis'],'official-release-listing')
        self.assertEqual(REVIEW['reviewDecision'],'approve')
        new=[a for a in CATALOG['artists'] if a['id'] not in REVIEW['baselineArtistIds']]
        self.assertEqual({a['name']:len(a['albums']) for a in new},COUNTS)
        self.assertEqual(REVIEW['counts'],COUNTS)
        self.assertEqual(len(set(COUNTS.values())),6)
        self.assertEqual(set(REVIEW['genres'].values()),{'jazz','rock','metal','techno','pop','Japanese pop'})
        self.assertEqual(len(CATALOG['artists']),20);self.assertEqual(sum(len(a['albums']) for a in CATALOG['artists']),292)
        evidence={w['catalogId']:w for w in REVIEW['works']};self.assertEqual(len(evidence),93)
        for artist in new:
            self.assertTrue(artist['aliases'])
            for album in artist['albums']:
                with self.subTest(title=album['title']):
                    w=evidence[album['id']]
                    for field in ['title','label','sourceUrl','sourceName']:self.assertEqual(album[field],w[field])
                    self.assertEqual(artist['id'],w['artistId']);self.assertEqual(artist['name'],w['artist'])
                    self.assertEqual(album['year'],w['displayYear']);self.assertEqual(album['evidenceFile'],FILE)
                    self.assertEqual(album['checkedAt'],REVIEW['checkedAt']);self.assertEqual(album['reviewer'],REVIEW['reviewer'])
                    self.assertTrue(album['official']);self.assertEqual(album['scope'],'work')
                    self.assertTrue(w['officialListingConfirmed']);self.assertEqual(w['listedAs'],'album')
                    url=urlsplit(album['sourceUrl']);self.assertEqual(url.scheme,'https')
                    self.assertIn(url.hostname,{'www.universal-music.co.jp','wmg.jp'})
                    self.assertRegex(w['sourceSha256'],r'^[a-f0-9]{64}$')
                    released=w['sourceReleaseDate']
                    if len(released)==10:self.assertLessEqual(date.fromisoformat(released),date.fromisoformat(REVIEW['checkedAt']))
                    else:self.assertLessEqual(int(released),int(REVIEW['checkedAt'][:4]))
                    self.assertNotIn('thumbnail',album);self.assertNotIn('listeningLink',album)

    def test_upcoming_editions_tribute_solo_video_and_duplicate_formats_are_not_added(self):
        new=[a for a in CATALOG['artists'] if a['id'] not in REVIEW['baselineArtistIds']]
        titles=[a['title'] for artist in new for a in artist['albums']]
        for forbidden in ['MR. バッド・ガイ','スター・フリート','アウトサイダー・ツアー','宇多田ヒカルのうた','LIVE CHRONICLES','denver luna','Juanita 2022']:
            self.assertFalse(any(forbidden in title for title in titles),forbidden)
        approved_pages={w.get('albumPageUrl',w['sourceUrl']).rstrip('/') for w in REVIEW['works']}
        future=[w for w in REVIEW['excludedCandidates'] if w.get('sourceReleaseDate','')>REVIEW['checkedAt']]
        self.assertEqual(len(future),5)
        for held in future:self.assertNotIn(held['sourceUrl'].rstrip('/'),approved_pages)
        for artist in CATALOG['artists']:
            keys=[re.sub(r'[^\w]','',a['title'].casefold()) for a in artist['albums']]
            self.assertEqual(len(keys),len(set(keys)))
        self.assertNotIn("B’z",[a['name'] for a in CATALOG['artists']])

    def test_original_work_years_and_reissue_dates_stay_distinct(self):
        works={w['title']:w for w in REVIEW['works']}
        self.assertEqual(works['オペラ座の夜']['displayYear'],'1975')
        self.assertEqual(works['オペラ座の夜']['sourceReleaseDate'],'2021-05-19')
        self.assertEqual(works['First Love']['displayYear'],'1999')
        self.assertEqual(works['First Love']['sourceReleaseDate'],'2022-03-10')
        self.assertEqual(works['Utada Hikaru SINGLE COLLECTION VOL.2']['displayYear'],'2010')
        self.assertEqual(works['Utada Hikaru SINGLE COLLECTION VOL.2']['sourceReleaseDate'],'2014-03-31')
        self.assertEqual(works['魔力の刻印 / THE NUMBER OF THE BEAST']['displayYear'],'1982')
        self.assertEqual(works['至上の愛']['displayYear'],'2018')

    def test_unverified_listening_keeps_search_without_blocking_release_recognition(self):
        checks=REVIEW['listeningChecks'];self.assertTrue(checks)
        self.assertTrue(all(c['decision']=='search' for c in checks))
        science=next(c for c in checks if c['title']=='SCIENCE FICTION')
        self.assertEqual(science['officialLinkUrl'],'https://umj.lnk.to/5sxLIA')
        self.assertEqual(science['linkPageTitle'],'SCIENCE FICTION【アナログ盤】')
        self.assertRegex(science['linkPageSha256'],r'^[a-f0-9]{64}$')
        self.assertEqual(sum(bool(a.get('listeningLink')) for artist in CATALOG['artists'] for a in artist['albums']),6)
if __name__=='__main__':unittest.main()
