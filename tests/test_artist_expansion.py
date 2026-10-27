"""Reviewed official sources, additive catalog and distinct release/listening decisions."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]
CATALOG=json.loads((ROOT/'data/official-catalog.json').read_text())
# This review describes the historical 18-work batch; depth additions have their own review/tests.
for artist in CATALOG['artists']:
    artist['albums']=[a for a in artist['albums'] if not a['id'].startswith('official:depth-20261027:')]
FILE='data/official-reviews/artist-expansion-2026-10-27.json'
REVIEW=json.loads((ROOT/FILE).read_text())
class ArtistExpansion(unittest.TestCase):
    def test_original_hundred_and_artist_metadata_are_unchanged(self):
        old=copy.deepcopy(CATALOG)
        old['artists']=[a for a in old['artists'] if a['id'] in REVIEW['baselineArtistIds']]
        self.assertEqual(len(old['artists']),5)
        self.assertEqual(sum(len(a['albums']) for a in old['artists']),100)
        digest=hashlib.sha256(json.dumps(old,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(digest,REVIEW['baselineCatalogFingerprint'])

    def test_nine_new_artists_have_two_approved_official_albums_each(self):
        self.assertEqual(REVIEW['recognitionBasis'],'official-release-listing')
        new=[a for a in CATALOG['artists'] if a['id'] not in REVIEW['baselineArtistIds']]
        self.assertEqual({a['name'] for a in new},{'The Beatles','Led Zeppelin','Black Sabbath','Metallica','Kraftwerk','Daft Punk','David Bowie','Michael Jackson','Ryuichi Sakamoto'})
        self.assertEqual(len(CATALOG['artists']),14)
        self.assertEqual(sum(len(a['albums']) for a in CATALOG['artists']),118)
        self.assertNotIn("B’z",str(new));self.assertNotIn('B\'z',str(new))
        self.assertEqual(len(REVIEW['works']),18)
        evidence={w['catalogId']:w for w in REVIEW['works']}
        for artist in new:
            self.assertEqual(len(artist['albums']),2)
            self.assertTrue(artist['aliases'])
            for album in artist['albums']:
                with self.subTest(title=album['title']):
                    work=evidence[album['id']]
                    for field in ['title','label','sourceUrl','sourceName']:self.assertEqual(album[field],work[field])
                    self.assertEqual(album['year'],work['displayYear'])
                    self.assertEqual(artist['id'],work['artistId'])
                    self.assertEqual(album['checkedAt'],REVIEW['checkedAt'])
                    self.assertEqual(album['evidenceFile'],FILE)
                    self.assertTrue(album['official']);self.assertEqual(album['scope'],'work')
                    self.assertTrue(work['officialListingConfirmed']);self.assertEqual(work['listedAs'],'album')
                    source=urlsplit(album['sourceUrl']);self.assertEqual(source.scheme,'https')
                    self.assertIn(source.netloc,{'www.thebeatles.com','discography.ledzeppelin.com','www.universal-music.co.jp','www.metallica.com','wmg.jp','daftpunk.com','www.daftpunk.com','www.sonymusic.co.jp','www.commmons.com'})
                    if work['retrievalMethod']=='public-https-html':self.assertRegex(work['sourceSha256'],r'^[a-f0-9]{64}$')
                    else:
                        self.assertIn('403',work['rawHtmlRetrievalStatus'])
                        self.assertEqual(work['sourceObservationSha256'],hashlib.sha256(work['sourceObservation'].encode()).hexdigest())
                        self.assertNotIn('sourceSha256',work)
                    self.assertNotIn('thumbnail',album)

    def test_work_years_do_not_use_reissue_or_track_dates(self):
        works={w['title']:w for w in REVIEW['works']}
        self.assertEqual(works['Master of Reality（マスター・オブ・リアリティ）']['displayYear'],'1971')
        self.assertEqual(works['Master of Reality（マスター・オブ・リアリティ）']['sourceReleaseDate'],'2010-12-22')
        self.assertEqual(works['Computer World（コンピューター・ワールド）']['displayYear'],'1981')
        self.assertEqual(works['Hunky Dory（ハンキー・ドリー）']['displayYear'],'1971')
        self.assertEqual(works['async']['displayYear'],'2017')
        self.assertEqual(works['12']['sourceReleaseDate'],'2023-01-17')
        self.assertNotEqual(works['12']['displayYear'],'2022')

    def test_only_identity_checked_album_is_promoted_and_restricted_sources_stay_documented(self):
        new=[a for a in CATALOG['artists'] if a['id'] not in REVIEW['baselineArtistIds']]
        linked=[(artist,album) for artist in new for album in artist['albums'] if album.get('listeningLink')]
        self.assertEqual(len(linked),1)
        artist,album=linked[0];link=album['listeningLink'];check=REVIEW['listeningChecks'][0]
        self.assertEqual((artist['name'],album['title']),('Daft Punk','Discovery'))
        self.assertEqual(link['url'],check['canonicalUrl']);self.assertIn(link['url'],check['listedTargetUrl'])
        self.assertEqual(link['target'],check['target']);self.assertEqual(link['officialSourceUrl'],album['sourceUrl'])
        self.assertEqual(link['target']['artist'],artist['name']);self.assertEqual(link['target']['title'],album['title'])
        self.assertEqual(link['target']['type'],'music.album');self.assertFalse(check['playbackVerified'])
        for field in ['sourceSha256','linkPageSha256','targetSha256']:self.assertRegex(link[field],r'^[a-f0-9]{64}$')
        held=next(c for c in REVIEW['listeningChecks'] if c['title']=='Abbey Road')
        self.assertEqual(held['decision'],'search');self.assertEqual(held['observedTargetTitle'],'Abbey Road (Super Deluxe Edition)')
        self.assertTrue(any('403' in f['error'] for f in REVIEW['retrievalFailures']))
        self.assertEqual(sum(bool(a.get('listeningLink')) for artist in CATALOG['artists'] for a in artist['albums']),4)
if __name__=='__main__':unittest.main()
