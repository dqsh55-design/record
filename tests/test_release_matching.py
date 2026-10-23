import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from release_matching import release_evidence, supported_group


class ReleaseMatchingTests(unittest.TestCase):
    def setUp(self):
        self.group = {'title': 'Album', 'primary-type': 'Album'}
        self.detail = {'title': 'Album', 'artists': [{'name': 'Artist'}], 'label': 'Label',
                       'tracks': [{'title': 'One'}, {'title': 'Two'}]}
        self.release = {'id': 'release-id', 'status': 'Official',
                        'artist-credit': [{'artist': {'name': 'Artist'}}],
                        'label-info': [{'label': {'name': 'Label'}, 'catalog-number': 'ABC-1'}],
                        'media': [{'tracks': [{'title': 'One'}, {'title': 'Two'}]}]}

    def check(self, releases=None):
        return release_evidence(self.group, self.detail, releases or [self.release], ['Artist'])

    def test_positive_studio_live_compilation_reissue(self):
        for types in ([], ['Live'], ['Compilation']):
            self.group['secondary-types'] = types
            result = self.check()
            self.assertEqual(result['status'], 'corroborated')
            self.assertEqual(result['releases'][0]['catalog_numbers'], ['ABC-1'])

    def test_title_artist_only_is_candidate(self):
        self.detail.pop('label')
        self.assertEqual(self.check()['status'], 'candidate')

    def test_bootleg_is_never_corroborated(self):
        self.release['status'] = 'Bootleg'
        self.assertEqual(self.check()['status'], 'candidate')

    def test_wrong_artist_or_detail_title(self):
        self.detail['artists'] = [{'name': 'Other'}]
        self.assertEqual(self.check()['status'], 'candidate')
        self.detail['artists'] = [{'name': 'Artist'}]
        self.detail['title'] = 'Different'
        self.assertEqual(self.check()['status'], 'candidate')

    def test_track_order_bonus_and_empty_tracks(self):
        for tracks in ([{'title': 'Two'}, {'title': 'One'}], [], [{'title': 'One'}]):
            self.detail['tracks'] = tracks
            self.assertEqual(self.check()['status'], 'candidate')

    def test_evidence_cannot_be_combined_across_editions(self):
        other = copy.deepcopy(self.release)
        other['label-info'][0]['label']['name'] = 'Other'
        self.release['media'] = []
        self.assertEqual(self.check([self.release, other])['status'], 'candidate')

    def test_unknown_labels_and_missing_release_credit(self):
        self.release['label-info'][0]['label']['name'] = '[no label]'
        self.assertEqual(self.check()['status'], 'candidate')
        self.release['label-info'][0]['label']['name'] = 'Label'
        self.release.pop('artist-credit')
        self.assertEqual(self.check()['status'], 'candidate')

    def test_unsupported_types(self):
        for group in ({'primary-type': 'Single'}, {'primary-type': 'Album', 'secondary-types': ['DJ-mix']}):
            self.assertFalse(supported_group(group))

if __name__ == '__main__':
    unittest.main()
