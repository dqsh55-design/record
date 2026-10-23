import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from automatic_matching import youtube_evidence, compare, verify_album, enrich

class AutomaticTests(unittest.TestCase):
    def setUp(self):
        self.detail = {'title': 'Album', 'artists': [{'name': 'Artist'}], 'label': 'Label',
                       'trackCount': 2, 'tracks': [{'title': 'One'}, {'title': 'Two'}]}
        self.release = {'id': 'edition', 'title': 'Album', 'status': 'Official',
                        'artist-credit': [{'artist': {'name': 'Artist'}}],
                        'label-info': [{'label': {'name': 'Label'}}], 'medium-count': 1,
                        'media': [{'position': 1, 'track-count': 2, 'tracks': [
                            {'position': 1, 'title': 'One'}, {'position': 2, 'title': 'Two'}]}]}
        self.music = Mock()
        self.music.get_album.return_value = self.detail
        self.mb = Mock()
        self.mb.get.side_effect = lambda path, **kw: {'releases': [{'id': 'edition'}], 'count': 1} if path == 'release/' else self.release
        self.album = {'id': 'MPREb_test', 'title': 'Album', 'url': 'keep', 'match_evidence': {'saved': True}}

    def check(self):
        return compare(youtube_evidence('MPREb_test', self.detail), self.release)

    def test_sufficient_requires_every_check_from_same_release(self):
        self.assertEqual(self.check()['status'], 'supported')
        self.release['label-info'][0]['label']['name'] = 'Other'
        self.assertEqual(self.check()['status'], 'different')

    def test_missing_label_description_never_infers_publisher(self):
        self.detail.pop('label')
        self.detail['description'] = 'Provided to YouTube by Label. ℗ Label'
        result = self.check()
        self.assertEqual(result['status'], 'insufficient')
        self.assertEqual(result['checks']['order'], 'match')
        self.assertEqual(result['checks']['label'], 'unknown')

    def test_partial_disc_or_album_is_unknown(self):
        for obj, field in [(self.detail, 'trackCount'), (self.release, 'medium-count'), (self.release['media'][0], 'track-count')]:
            old = obj.pop(field)
            self.assertEqual(self.check()['status'], 'insufficient')
            obj[field] = old

    def test_order_count_title_artist_and_bootleg_mismatches(self):
        self.detail['tracks'].reverse()
        self.assertEqual(self.check()['checks']['order'], 'different')
        self.assertEqual(self.check()['checks']['titles'], 'match')
        self.detail['tracks'].append({'title': 'Bonus'})
        self.detail['trackCount'] = 3
        self.assertEqual(self.check()['checks']['count'], 'different')
        self.release['status'] = 'Bootleg'
        self.assertEqual(self.check()['status'], 'different')

    def test_unknown_label_placeholders(self):
        for value in (' [no label] ', '[unknown]', ''):
            self.detail['label'] = value
            self.release['label-info'][0]['label']['name'] = value
            self.assertEqual(self.check()['status'], 'insufficient')

    def test_failure_never_keeps_positive_status(self):
        self.music.get_album.side_effect = OSError('offline')
        result = verify_album(self.album, self.music, self.mb)
        self.assertEqual(result['status'], 'insufficient')
        self.assertTrue(result['limitations'])
        self.mb.get.assert_not_called()

    def test_search_is_candidate_only_and_truncation_is_not_global_mismatch(self):
        self.release['title'] = 'Different'
        result = verify_album(self.album, self.music, self.mb)
        self.assertEqual(result['status'], 'different')
        self.mb.get.side_effect = lambda path, **kw: {'releases': [{'id': 'edition'}], 'count': 99} if path == 'release/' else self.release
        self.assertEqual(verify_album(self.album, self.music, self.mb)['status'], 'insufficient')

    def test_multiple_candidates_do_not_combine_evidence(self):
        a, b = copy.deepcopy(self.release), copy.deepcopy(self.release)
        a['label-info'] = []
        b['media'] = []
        self.mb.get.side_effect = [{'releases': [{'id': 'a'}, {'id': 'b'}], 'count': 2}, a, b]
        self.assertEqual(verify_album(self.album, self.music, self.mb)['status'], 'insufficient')

    def test_all_catalog_artists_are_eligible_and_data_retained(self):
        second = {**self.album, 'id': 'MPREb_second'}
        catalog = {'one': [self.album], 'two': [second]}
        enrich(catalog, self.music, self.mb, max_albums=1)
        self.assertIn('automatic_verification', self.album)
        self.assertNotIn('automatic_verification', second)
        enrich(catalog, self.music, self.mb, max_albums=1)
        self.assertIn('automatic_verification', second)
        self.assertEqual(self.album['url'], 'keep')
        self.assertEqual(self.album['match_evidence'], {'saved': True})

    def test_multidisc_tracks_use_disc_then_track_order(self):
        self.release['medium-count'] = 2
        self.release['media'] = [
            {'position': 2, 'track-count': 1, 'tracks': [{'position': 1, 'title': 'Two'}]},
            {'position': 1, 'track-count': 1, 'tracks': [{'position': 1, 'title': 'One'}]}]
        self.assertEqual(self.check()['status'], 'supported')

if __name__ == '__main__':
    unittest.main()
