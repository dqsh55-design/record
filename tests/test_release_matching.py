import ast
import json
import copy
from unittest.mock import Mock, patch
import urllib.parse
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
        return release_evidence(self.group, self.detail, [self.release] if releases is None else releases, ['Artist'])

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

    def test_partial_tracklists_are_not_corroborated(self):
        self.detail['trackCount'] = 3
        self.assertEqual(self.check()['status'], 'candidate')
        self.detail['trackCount'] = 2
        self.release['media'][0]['track-count'] = 3
        self.assertEqual(self.check()['status'], 'candidate')
        self.release['media'][0]['track-count'] = 2
        self.release['medium-count'] = 2
        self.assertEqual(self.check()['status'], 'candidate')

    def test_unrelated_collaborator_is_not_exact_artist_match(self):
        self.detail['artists'].append({'name': 'Unrelated Artist'})
        self.assertEqual(self.check()['status'], 'candidate')
        self.detail['artists'].pop()
        self.release['artist-credit'].append({'artist': {'name': 'Unrelated Artist'}})
        self.assertEqual(self.check()['status'], 'candidate')

    def test_no_releases_and_padded_placeholder(self):
        self.assertEqual(self.check([])['status'], 'candidate')
        self.detail['label'] = '[no label]'
        self.release['label-info'][0]['label']['name'] = ' [no label] '
        self.assertEqual(self.check()['status'], 'candidate')

    def test_unsupported_types(self):
        for group in ({'primary-type': 'Single'}, {'primary-type': 'Album', 'secondary-types': ['DJ-mix']}):
            self.assertFalse(supported_group(group))

class BridgeFailureTests(unittest.TestCase):
    def test_release_api_failure_retains_new_candidate(self):
        # Load the bridge without executing the catalog-writing entry point.
        source = Path('scripts/build_catalog.py').read_text()
        tree = ast.parse(source)
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'bridge_discography')
        group = {'id': 'group', 'title': 'Album', 'primary-type': 'Album'}
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({'release-groups': [group]})
        music = Mock()
        music.search.return_value = [{'browseId': 'MPREb_test', 'title': 'Album', 'artists': [{'name': 'Artist'}]}]
        music.get_album.return_value = {'title': 'Album', 'artists': [{'name': 'Artist'}], 'tracks': [{'title': 'One'}]}
        import urllib.request
        namespace = dict(urllib=urllib, json=json, music=music, artist_aliases={},
                         supported_group=supported_group, release_evidence=release_evidence,
                         title_key=lambda s: s.casefold(), time=Mock(),
                         musicbrainz_json=Mock(side_effect=OSError('offline')))
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<bridge>', 'exec'), namespace)
        with patch('urllib.request.urlopen', return_value=response):
            albums, diagnostics = namespace['bridge_discography']('Artist', 'artist-id')
        self.assertEqual(len(albums), 1)
        self.assertEqual(albums[0]['match_evidence']['status'], 'candidate')
        self.assertEqual(albums[0]['url'], 'https://music.youtube.com/browse/MPREb_test')
        self.assertEqual(diagnostics['release_errors'][0]['error'], 'offline')

if __name__ == '__main__':
    unittest.main()
