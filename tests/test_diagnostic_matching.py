"""Diagnostics preserve uncertainty and collect MB even when YouTube fails."""
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from diagnose_matching import diagnose, failure


class DiagnosticTests(unittest.TestCase):
    def test_proxy_failure_still_fetches_real_candidate_details(self):
        music = Mock()
        music.get_album.side_effect = URLError(OSError('Tunnel connection failed: 403 Forbidden'))
        mb = Mock()
        release = {'id': 'edition', 'title': 'Album', 'status': 'Official',
                   'artist-credit': [{'artist': {'name': 'Artist'}}],
                   'label-info': [{'label': {'name': 'Label'}}],
                   'media': [{'position': 1, 'track-count': 1,
                              'tracks': [{'position': 1, 'title': 'Song'}]}]}
        mb.get.side_effect = lambda path, **kw: {'count': 40, 'releases': [{'id': 'edition'}]} if path == 'release/' else release
        report = diagnose(music, mb)
        self.assertEqual(mb.get.call_count, 6)
        for target in report['targets']:
            self.assertEqual(target['status'], 'insufficient')
            self.assertEqual(target['youtube_error']['category'], 'proxy_connect_403')
            self.assertFalse(target['comparison_available'])
            self.assertEqual(target['candidates'][0]['track_count'], 1)
            self.assertEqual(target['candidates'][0]['checks']['title'], 'unknown')
            self.assertNotIn('youtube', target)

    def test_errors_do_not_export_proxy_credentials(self):
        error = URLError('proxy http://user:secret@example.invalid:8080 denied')
        self.assertNotIn('secret', str(failure(error)))


if __name__ == '__main__':
    unittest.main()
