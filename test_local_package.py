import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from package_local import package


class LocalPackage(unittest.TestCase):
    def fixture(self, root, extra=None):
        payload = root / 'payload'
        payload.mkdir()
        files = {'Start-Cover.cmd': b'echo fixture', 'BUILD.json': b'{"redistribution_ready":false}'}
        files.update(extra or {})
        manifest = {}
        for name, content in files.items():
            path = payload / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            manifest[name] = {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
        (payload / 'MANIFEST.json').write_text(json.dumps(manifest))
        return payload

    def test_private_backup_does_not_change_redistribution_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = self.fixture(root)
            target = root / 'local.zip'
            package(payload, target)
            with zipfile.ZipFile(target) as archive:
                self.assertIsNone(archive.testzip())
                self.assertFalse(json.loads(archive.read('AI-Cover-Lab/BUILD.json'))['redistribution_ready'])
                self.assertIn('AI-Cover-Lab/LOCAL_USE.md', archive.namelist())
                self.assertIn('AI-Cover-Lab/LOCAL_USE.txt', archive.namelist())
            self.assertTrue(target.with_suffix('.zip.sha256').read_text().startswith(hashlib.sha256(target.read_bytes()).hexdigest()))

    def test_changed_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = self.fixture(root)
            (payload / 'Start-Cover.cmd').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'File changed'):
                package(payload, root / 'local.zip')

    def test_raw_audio_is_rejected_even_under_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = self.fixture(root, {'runtime/private.wav': b'private'})
            with self.assertRaisesRegex(ValueError, 'Audio recordings'):
                package(payload, root / 'local.zip')

    def test_same_size_changed_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = self.fixture(root)
            path = payload / 'Start-Cover.cmd'
            path.write_bytes(b'X' * path.stat().st_size)
            target = root / 'local.zip'
            with self.assertRaisesRegex(ValueError, 'File changed'):
                package(payload, target)
            self.assertFalse(target.exists())

    def test_unexpected_training_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = self.fixture(root, {'training/private/profile.json': b'private'})
            with self.assertRaisesRegex(ValueError, 'Unexpected training'):
                package(payload, root / 'local.zip')


if __name__ == '__main__':
    unittest.main()
