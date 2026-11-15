"""install.sh: the rollback of a failed update and the backup pruning, run
in sh against a temporary /mnt/UDISK (the functions are cut out of the
installer, so this tests the real code)."""
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

INSTALL = pathlib.Path(__file__).parents[1] / "install.sh"
SH = shutil.which("sh")


def functions(udisk):
    text = INSTALL.read_text()
    start = text.index("STAGE_DIRS=")
    end = text.index("# Remove master-server")
    return text[start:end].replace("/mnt/UDISK", udisk)


def write(path, text="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@unittest.skipIf(SH is None, "no sh")
class InstallStagingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.udisk = pathlib.Path(self.tmp.name)
        self.build = self.udisk / "k2-build"
        self.backups = self.udisk / "openklipper-backups"

    def tearDown(self):
        self.tmp.cleanup()

    def run_sh(self, body, backup, env=None):
        script = ("set -eu\nBUILD=%s\nBACKUP=%s\n%s\n%s\n" % (
            self.build, backup, functions(str(self.udisk)), body))
        return subprocess.run([SH, "-c", script], capture_output=True,
                              text=True, env=dict(os.environ, **(env or {})))

    def test_a_failure_after_the_swap_restores_the_previous_version(self):
        backup = self.backups / "20261115-100000"
        write(self.build / "VERSION", "old")
        write(self.udisk / "harkscreen" / "VERSION", "old")
        write(self.build.with_name("k2-build.okl-new") / "VERSION", "new")
        write(self.udisk / "harkscreen.okl-new" / "VERSION", "new")
        backup.mkdir(parents=True)
        res = self.run_sh(
            'SWAPPED=1\n'
            'mv "$BUILD" "$BACKUP/build.previous"\n'
            'mv "$BUILD.okl-new" "$BUILD"\n'
            'mv %(u)s/harkscreen "$BACKUP/harkscreen.previous"\n'
            'mv %(u)s/harkscreen.okl-new %(u)s/harkscreen\n'
            'false   # a later step fails\n' % {"u": self.udisk}, backup)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("previous version back", res.stderr)
        self.assertEqual((self.build / "VERSION").read_text(), "old")
        self.assertEqual((self.udisk / "harkscreen" / "VERSION").read_text(),
                         "old")
        self.assertFalse((backup / "build.previous").exists())

    def test_a_failure_before_the_swap_only_removes_the_staged_copy(self):
        write(self.build / "VERSION", "old")
        write(self.build.with_name("k2-build.okl-new") / "VERSION", "new")
        write(self.udisk / "harkcam.okl-new" / "x")
        res = self.run_sh("false", self.backups / "20261115-100000")
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual((self.build / "VERSION").read_text(), "old")
        self.assertFalse(self.build.with_name("k2-build.okl-new").exists())
        self.assertFalse((self.udisk / "harkcam.okl-new").exists())

    def test_a_finished_install_is_never_rolled_back(self):
        backup = self.backups / "20261115-100000"
        write(self.build / "VERSION", "new")
        write(backup / "build.previous" / "VERSION", "old")
        res = self.run_sh("SWAPPED=1\nDONE=1\nexit 0", backup)
        self.assertEqual(res.returncode, 0)
        self.assertEqual((self.build / "VERSION").read_text(), "new")

    def test_pruning_keeps_the_first_and_the_newest(self):
        stamps = ["20260801-100000", "20260901-100000", "20261001-100000",
                  "20261101-100000", "20261110-100000", "20261115-100000"]
        for st in stamps:
            write(self.backups / st / "app.init")
            write(self.backups / st / "build.previous" / "VERSION")
        write(self.backups / "LATEST", str(self.backups / stamps[-1]))
        res = self.run_sh("DONE=1\nprune_backups",
                          self.backups / stamps[-1])
        self.assertEqual(res.returncode, 0, res.stderr)
        left = sorted(p.name for p in self.backups.iterdir() if p.is_dir())
        self.assertEqual(left, [stamps[0]] + stamps[-3:])
        # the first keeps Creality's originals, not its old build copy
        self.assertTrue((self.backups / stamps[0] / "app.init").exists())
        self.assertFalse((self.backups / stamps[0] / "build.previous")
                         .exists())
        self.assertTrue((self.backups / stamps[-1] / "build.previous")
                        .exists())

    def test_pruning_with_few_backups_changes_nothing(self):
        for st in ("20261101-100000", "20261115-100000"):
            write(self.backups / st / "build.previous" / "VERSION")
        res = self.run_sh("DONE=1\nprune_backups",
                          self.backups / "20261115-100000")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue((self.backups / "20261101-100000" /
                         "build.previous").exists())

    def test_keep_setting(self):
        stamps = ["20261101-10000%d" % i for i in range(5)]
        for st in stamps:
            write(self.backups / st / "app.init")
        res = self.run_sh("DONE=1\nprune_backups", self.backups / stamps[-1],
                          env={"OKL_KEEP_BACKUPS": "1"})
        self.assertEqual(res.returncode, 0, res.stderr)
        left = sorted(p.name for p in self.backups.iterdir())
        self.assertEqual(left, [stamps[0], stamps[-1]])


if __name__ == "__main__":
    unittest.main()
