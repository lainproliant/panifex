# --------------------------------------------------------------------
# test_examples.py
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Saturday September 26, 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------

import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from panifex import BuildEngine, sh


# --------------------------------------------------------------------
class ExamplesTests(unittest.TestCase):
    def setUp(self):
        self.olddir = Path.cwd()
        self.tempdir = tempfile.TemporaryDirectory()
        os.chdir(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()
        os.chdir(self.olddir)

    def test_hello_world(self):
        engine = BuildEngine()
        target = engine.target

        @target
        def hello():
            return sh("echo 'Hello' >> {output}", output="hello.txt")

        @target
        def world():
            return sh("echo 'World' >> {output}", output="world.txt")

        @target
        def hello_world(hello, world):
            return sh(
                "cat {input} >> {output}", input=[hello, world], output="helloworld.txt"
            )

        recipes = engine.compile_targets(["hello_world"])
        loop = asyncio.get_event_loop()
        loop.run_until_complete(engine.resolve(recipes))

        with open('helloworld.txt', 'r') as infile:
            self.assertEqual(infile.read().strip(), 'Hello\nWorld')


# --------------------------------------------------------------------
if __name__ == "__main__":
    unittest.main()
