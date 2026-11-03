"""Security regressions; no root or changes outside a temporary directory."""
import importlib.util
from pathlib import Path
import tempfile
import multiprocessing
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('kach', Path(__file__).resolve().parents[1] / 'kachaning.py')
k = importlib.util.module_from_spec(spec)
spec.loader.exec_module(k)

class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lock_patch = patch.object(k, 'ADMIN_LOCK', str(Path(self.tmp.name) / 'admin.lock'))
        self.lock_patch.start()
        self.addCleanup(self.lock_patch.stop)

    def test_admin_lock_serializes_processes(self):
        ctx = multiprocessing.get_context('fork')
        entered, release, second = ctx.Event(), ctx.Event(), ctx.Event()
        @k.serialized_admin
        def first():
            entered.set()
            release.wait(5)
        @k.serialized_admin
        def other():
            second.set()
        a, b = ctx.Process(target=first), ctx.Process(target=other)
        a.start()
        try:
            self.assertTrue(entered.wait(3))
            b.start()
            self.assertFalse(second.wait(.2))
            release.set()
            self.assertTrue(second.wait(3))
        finally:
            release.set()
            for proc in (a, b):
                if proc.pid:
                    proc.join(3)
                    if proc.is_alive():
                        proc.terminate()
                        proc.join()
        self.assertEqual(a.exitcode, 0)
        self.assertEqual(b.exitcode, 0)

    def test_explicit_unlimited_grant_is_preserved(self):
        with patch.object(k, 'read_state', return_value={'admin': {'granted': True, 'expires': None}}), patch.object(k, 'root_revoke') as revoke:
            k.root_expire_check()
            revoke.assert_not_called()

    def test_key_read_error_does_not_erase_existing_keys(self):
        with patch.object(k, 'open', side_effect=PermissionError), patch.object(k, 'write_auth_keys') as write:
            with self.assertRaises(PermissionError):
                k.remove_helper_key('body')
            write.assert_not_called()

    def test_invalid_expiry_revokes(self):
        for value in ('tomorrow', float('nan'), float('inf'), True, 0):
            with self.subTest(value=value), patch.object(k, 'read_state', return_value={'admin': {'granted': True, 'expires': value}}), patch.object(k, 'root_revoke') as revoke:
                k.root_expire_check()
                revoke.assert_called_once()

    def test_root_copy_not_deleted_when_run_directly(self):
        with tempfile.TemporaryDirectory() as d:
            script = Path(d) / 'kachaning.py'
            script.write_text('timer source')
            with patch.object(k, '__file__', str(script)), patch.object(k, 'ROOT_COPY', str(script)), patch.object(k, 'ROOT_DIR', d), patch.object(k, 'open', create=True), patch.object(k, 'run', return_value=(0, '', '')):
                k.s_guard()
            self.assertTrue(script.exists())

    def test_arch_install_does_not_refresh_without_upgrade(self):
        with patch.object(k.shutil, 'which', side_effect=lambda name: name if name == 'pacman' else None), patch.object(k, 'run', return_value=(0, '', '')) as run:
            k.pkg_install(['x'], ['x'])
            self.assertNotIn('-Sy', run.call_args.args[0])

if __name__ == '__main__':
    unittest.main()
