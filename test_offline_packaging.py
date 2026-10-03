import hashlib
import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from build_offline import archive, validate_corresponding_sources


class SourceAuditGate(unittest.TestCase):
    def fixture(self, root):
        source = root / 'source.txt'
        source.write_bytes(b'test source')
        entry = {'status': 'complete', 'archive': source.name,
                 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
        manifest = {name: dict(entry) for name in ['ffmpeg', 'pedalboard', 'soxr', 'libsndfile', 'runtime']}
        manifest['ffmpeg'].update(build_recipe_archive=source.name, build_recipe_sha256=entry['sha256'],
                                  dependency_cache_archive=source.name,
                                  dependency_cache_expected_sha256=entry['sha256'])
        manifest['libsndfile'].update(wrapper_source_archive=source.name,
                                     wrapper_source_sha256=entry['sha256'],
                                     dependency_source_archive=source.name,
                                     dependency_source_sha256=entry['sha256'])
        return manifest

    def write(self, root, manifest):
        (root / 'SOURCE-MANIFEST.json').write_text(json.dumps(manifest), encoding='utf-8-sig')

    def test_all_source_checks_accept_bom_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self.fixture(root)
            self.write(root, manifest)
            self.assertEqual(validate_corresponding_sources(root), manifest)

    def test_native_and_runtime_audits_fail_closed(self):
        for component in ['ffmpeg', 'pedalboard', 'soxr', 'libsndfile', 'runtime']:
            with self.subTest(component=component), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                manifest = self.fixture(root)
                manifest[component]['status'] = 'pending'
                self.write(root, manifest)
                with self.assertRaisesRegex(RuntimeError, 'audit is incomplete'):
                    validate_corresponding_sources(root)

    def test_missing_dependency_declaration_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self.fixture(root)
            del manifest['ffmpeg']['dependency_cache_archive']
            self.write(root, manifest)
            with self.assertRaisesRegex(RuntimeError, 'declaration is incomplete'):
                validate_corresponding_sources(root)

    def test_corrupt_dependency_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self.fixture(root)
            manifest['libsndfile']['dependency_source_sha256'] = '0' * 64
            self.write(root, manifest)
            with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                validate_corresponding_sources(root)

    def test_source_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self.fixture(root)
            manifest['runtime']['archive'] = '../outside.zip'
            self.write(root, manifest)
            with self.assertRaisesRegex(RuntimeError, 'escapes the source folder'):
                validate_corresponding_sources(root)


class ArchiveSafety(unittest.TestCase):
    def fixture(self, root, ready=True):
        payload = root / 'AI-Cover-Lab'
        payload.mkdir()
        (payload / 'BUILD.json').write_text(json.dumps({'redistribution_ready': ready}))
        return payload

    def test_local_test_bundle_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, 'not been cleared'):
                archive(self.fixture(root, False), root)

    def test_split_archive_reassembles_exactly(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = self.fixture(root)
            (payload / 'random.bin').write_bytes(os.urandom(1300000))
            archive(payload, root, part_mib=1)
            manifest = json.loads((root / 'offline-manifest.json').read_text())
            combined = b''.join((root / part['name']).read_bytes() for part in manifest['parts'])
            self.assertEqual(len(manifest['parts']), 2)
            self.assertEqual(hashlib.sha256(combined).hexdigest(), manifest['sha256'])
            self.assertTrue(all(part['bytes'] <= 1024 * 1024 for part in manifest['parts']))

    def test_unexpected_training_audio_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = self.fixture(root)
            private = payload / 'training/private/input.wav'
            private.parent.mkdir(parents=True)
            private.write_bytes(b'private')
            with self.assertRaisesRegex(RuntimeError, 'private data'):
                archive(payload, root)


@unittest.skipUnless(os.name == 'nt', 'Windows offline installer')
class OfflineInstaller(unittest.TestCase):
    def install(self, root, destination, entry='AI-Cover-Lab/hello.txt', corrupt=False):
        archive = root / 'AI-Cover-Lab-Windows-offline.zip'
        with zipfile.ZipFile(archive, 'w') as stream:
            stream.writestr(entry, 'test')
        data = archive.read_bytes()
        part = root / (archive.name + '.part01')
        part.write_bytes(data)
        archive.unlink()
        sha = hashlib.sha256(data).hexdigest()
        (root / 'offline-manifest.json').write_text(json.dumps({
            'archive': archive.name, 'bytes': len(data), 'sha256': sha,
            'parts': [{'name': part.name, 'bytes': len(data), 'sha256': '0' * 64 if corrupt else sha}]}))
        script = root / 'install-offline.ps1'
        script.write_bytes(Path(__file__).with_name('install-offline.ps1').read_bytes())
        return subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                               '-File', str(script), '-Destination', str(destination)],
                              capture_output=True, timeout=30)

    def test_join_verify_extract_path_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix='offline test ') as temporary:
            root = Path(temporary)
            destination = root / 'new install'
            result = self.install(root, destination)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((destination / 'AI-Cover-Lab/hello.txt').read_text(), 'test')

    def test_corrupt_part_never_extracts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / 'new'
            self.assertNotEqual(self.install(root, destination, corrupt=True).returncode, 0)
            self.assertFalse(destination.exists())

    def test_traversal_never_extracts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / 'new'
            self.assertNotEqual(self.install(root, destination, 'AI-Cover-Lab/../../escape.txt').returncode, 0)
            self.assertFalse(destination.exists())
            self.assertFalse((root / 'escape.txt').exists())

    def test_existing_install_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / 'existing'
            destination.mkdir()
            sentinel = destination / 'keep.txt'
            sentinel.write_text('keep')
            self.assertNotEqual(self.install(root, destination).returncode, 0)
            self.assertEqual(sentinel.read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
