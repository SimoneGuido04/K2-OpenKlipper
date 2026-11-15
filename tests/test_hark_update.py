import importlib.util
import io
import json
import pathlib
import sys
import types
import unittest
from unittest import mock


EXTRAS = pathlib.Path(__file__).parents[1] / "klippy" / "extras"

if "extras" not in sys.modules:
    package = types.ModuleType("extras")
    package.__path__ = [str(EXTRAS)]
    sys.modules["extras"] = package
spec = importlib.util.spec_from_file_location(
    "extras.hark_update", EXTRAS / "hark_update.py")
MODULE = importlib.util.module_from_spec(spec)
sys.modules["extras.hark_update"] = MODULE
spec.loader.exec_module(MODULE)


class ConfigError(Exception):
    pass


class FakeGcode:
    def __init__(self):
        self.out = []

    def register_command(self, *args, **kw):
        pass

    def respond_info(self, msg):
        self.out.append(msg)

    def respond_raw(self, msg):
        self.out.append(msg)


class FakeReactor:
    def monotonic(self):
        return 0.

    def register_async_callback(self, cb):
        cb(0.)


class FakePrinter:
    def __init__(self):
        self.gcode = FakeGcode()
        self.reactor = FakeReactor()

    def get_reactor(self):
        return self.reactor

    def lookup_object(self, name, default=None):
        return self.gcode if name == 'gcode' else default

    def register_event_handler(self, *args):
        pass


class FakeConfig:
    error = ConfigError

    def __init__(self, values=None):
        self.printer = FakePrinter()
        self.values = values or {}

    def get_printer(self):
        return self.printer

    def get(self, name, default=None):
        return self.values.get(name, default)

    def getfloat(self, name, default=None, **kw):
        return self.values.get(name, default)

    def getboolean(self, name, default=None):
        return self.values.get(name, default)


class CommandError(Exception):
    pass


class FakeGcmd:
    error = CommandError

    def __init__(self, params):
        self.params = params

    def get_int(self, name, default=None, **kw):
        return int(self.params.get(name, default))

    def respond_info(self, msg):
        pass


def releases(tag):
    body = json.dumps([{"tag_name": tag, "body": "notes",
                        "html_url": "https://example.invalid"}]).encode()
    return mock.patch.object(MODULE.urllib.request, "urlopen",
                             return_value=io.BytesIO(body))


class HarkUpdateTest(unittest.TestCase):
    def make(self, installed="0.4.25-alpha.1"):
        upd = MODULE.HarkUpdate(FakeConfig({'notify': False}))
        upd.status['installed'] = installed
        upd._installed = lambda: installed
        return upd

    def test_tag_pattern(self):
        for good in ("v0.4.25-alpha.1", "0.5.0", "v1.0.0-rc.2"):
            self.assertTrue(MODULE.TAG_RE.fullmatch(good), good)
        for bad in ("v1.0.0;reboot", "v1.0.0$(id)", "main", "v1.0.0 x",
                    "v1.0.0-alpha.1|sh", ""):
            self.assertFalse(MODULE.TAG_RE.fullmatch(bad), bad)

    def test_bad_repo_is_a_config_error(self):
        with self.assertRaises(ConfigError):
            MODULE.HarkUpdate(FakeConfig({'repo': 'a/b; reboot'}))

    def test_a_release_with_a_shell_tag_is_never_offered(self):
        upd = self.make()
        with releases("v9.9.9;reboot"):
            upd._check(None)
        self.assertFalse(upd.status['update_available'])
        self.assertIn("not a version", upd.status['error'])

    def test_good_release_is_offered(self):
        upd = self.make()
        with releases("v0.4.26-alpha.1"):
            upd._check(None)
        self.assertTrue(upd.status['update_available'])
        self.assertEqual(upd.status['latest'], "v0.4.26-alpha.1")

    def test_update_refuses_a_bad_tag_before_running_anything(self):
        upd = self.make()
        upd.status.update({'latest': "v9.9.9$(reboot)",
                           'update_available': True})
        with mock.patch.object(MODULE.subprocess, "Popen") as popen:
            with self.assertRaises(CommandError):
                upd.cmd_OKL_UPDATE(FakeGcmd({'CONFIRM': 1}))
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
