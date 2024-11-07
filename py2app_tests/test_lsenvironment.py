"""
Testcase for checking argv_emulation
"""

import ast  # noqa: F401
import os
import platform  # noqa: F401
import shutil
import signal  # noqa: F401
import subprocess
import sys
import time
import unittest

import py2app  # noqa: F401

from .tools import kill_child_processes

DIR_NAME = os.path.dirname(os.path.abspath(__file__))


class TestLSEnvironment(unittest.TestCase):
    py2app_args = []
    setup_file = "setup.py"
    app_dir = os.path.join(DIR_NAME, "app_with_environment")

    # Basic setup code
    #
    # The code in this block needs to be moved to
    # a base-class.
    @classmethod
    def setUpClass(cls):
        kill_child_processes()

        env = os.environ.copy()
        pp = os.path.dirname(os.path.dirname(py2app.__file__))
        if "PYTHONPATH" in env:
            env["PYTHONPATH"] = pp + ":" + env["PYTHONPATH"]
        else:
            env["PYTHONPATH"] = pp

        p = subprocess.Popen(
            [sys.executable, cls.setup_file, "py2app"] + cls.py2app_args,
            cwd=cls.app_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            close_fds=False,
            env=env,
        )
        lines = p.communicate()[0]
        if p.wait() != 0:
            print(lines)
            raise AssertionError("Creating basic_app bundle failed")

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(os.path.join(cls.app_dir, "build")):
            shutil.rmtree(os.path.join(cls.app_dir, "build"))

        if os.path.exists(os.path.join(cls.app_dir, "dist")):
            shutil.rmtree(os.path.join(cls.app_dir, "dist"))

        time.sleep(2)

    def tearDown(self):
        kill_child_processes()
        time.sleep(1)

    #
    # End of setup code
    #

    def test_basic_start(self):
        self.maxDiff = None

        path = os.path.join(self.app_dir, "dist/env.txt")
        if os.path.exists(path):
            os.unlink(path)

        path = os.path.join(self.app_dir, "dist/BasicApp.app")

        proc = subprocess.Popen(["/usr/bin/open", path])
        status = proc.wait()

        if status == 1:
            print("/usr/bin/open failed, retry")
            time.sleep(5)
            proc = subprocess.Popen(["/usr/bin/open", path])
            status = proc.wait()

        self.assertEqual(status, 0)

        path = os.path.join(self.app_dir, "dist/env.txt")
        for _ in range(70):  # Argv emulation can take up-to 60 seconds
            time.sleep(0.1)
            if os.path.exists(path):
                break

        self.assertTrue(os.path.isfile(path))

        fp = open(path)
        data = fp.read().strip()
        fp.close()

        env = ast.literal_eval(data)
        self.assertEqual(env["KNIGHT"], "ni!")
        self.assertEqual(env["EXTRA_VAR"], "hello world")
        self.assertEqual(env["LANG"], "nl_NL.latin1")
        self.assertEqual(env["LC_CTYPE"], "nl_NL.UTF-8")
