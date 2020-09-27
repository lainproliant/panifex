# --------------------------------------------------------------------
# test_artifacts.py
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Saturday September 26, 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------

import unittest
import panifex.artifacts

from pathlib import Path

# --------------------------------------------------------------------
class ArtifactsTests(unittest.TestCase):
    def test_digest_env(self):
        env = {
            'A': [1, 2, 3],
            'B': 'value',
            'C': ['alpha', 'beta', 'gamma']
        }

        result = panifex.artifacts.digest_env(env)
        self.assertEqual(result['A'], '1 2 3')
        self.assertEqual(result['B'], 'value')
        self.assertEqual(result['C'], 'alpha beta gamma')

    def test_digest_param(self):
        digest_param = panifex.artifacts.digest_param
        ValueArtifact = panifex.artifacts.ValueArtifact
        FileArtifact = panifex.artifacts.FileArtifact

        self.assertEqual(digest_param(1), ['1'])
        self.assertEqual(digest_param('alpha'), ['alpha'])
        self.assertEqual(digest_param(['alpha', 'beta', 'gamma']),
                         ['alpha', 'beta', 'gamma'])
        self.assertEqual(digest_param([
            Path('/a/b/c'),
            'oranges',
            ValueArtifact(1000),
            FileArtifact('/usr/bin/python')
        ]), [
            '/a/b/c',
            'oranges',
            '1000',
            '/usr/bin/python'
        ])

# --------------------------------------------------------------------
if __name__ == "__main__":
    unittest.main()
