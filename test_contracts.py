import tempfile
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

import exports
import voice_training as training
from audio_workflow import decode
from train_rvc import adapt_source
from voice_selection import resolve_source


class Contracts(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.patchers = [patch.object(training, 'ROOT', self.root / 'training'),
                         patch.object(training, 'APPLIO', self.root / 'backend'),
                         patch.object(exports, 'EXPORTS', self.root / 'exports')]
        for patcher in self.patchers:
            patcher.start()
        self.project = training.create_project('测试声线')
        self.source = self.root / 'audio.wav'
        t = np.arange(16000 * 4) / 16000
        sf.write(self.source, 0.2 * np.sin(2 * np.pi * 220 * t), 16000)

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.directory.cleanup()

    def test_path_validation(self):
        for invalid in ('../outside', '', 'a' * 13, 'Z' * 12):
            with self.assertRaises(ValueError):
                training.project_path(invalid)

    def test_portable_model_paths_and_traversal(self):
        folder = training.project_path(self.project)
        (folder / 'saved').mkdir()
        (folder / 'saved/voice.pth').write_bytes(b'model')
        data = training.read_project(self.project)
        data['active'] = {'model': 'saved/voice.pth'}
        training.write_json(folder / 'profile.json', data)
        self.assertEqual(training.active_model(self.project), (str(folder / 'saved/voice.pth'), ''))
        data['active']['model'] = '../escape.pth'
        training.write_json(folder / 'profile.json', data)
        with self.assertRaisesRegex(ValueError, '超出'):
            training.active_model(self.project)

    def test_duplicate_material_and_split_leak(self):
        training.add_materials(self.project, [str(self.source)], None, None)
        training.add_materials(self.project, [str(self.source)], None, None)
        self.assertEqual(len(training.read_project(self.project)['files']), 1)
        with self.assertRaisesRegex(ValueError, '重复'):
            training.add_materials(self.project, None, [str(self.source)], None)
        self.assertEqual(len(training.read_project(self.project)['files']), 1)

    def test_approval_requires_validation_and_listening(self):
        data = training.read_project(self.project)
        data['candidates'] = [{'id': 'candidate', 'model': 'model.pth', 'epoch': 1}]
        training.write_json(training.project_path(self.project) / 'profile.json', data)
        with self.assertRaisesRegex(ValueError, '试听'):
            training.approve(self.project, 'candidate', False)
        with self.assertRaisesRegex(ValueError, '技术检测'):
            training.approve(self.project, 'candidate', True)
        data['candidates'][0].update(tested=True, technical_pass=True)
        training.write_json(training.project_path(self.project) / 'profile.json', data)
        with self.assertRaisesRegex(ValueError, '跨声线'):
            training.approve(self.project, 'candidate', True)
        data['candidates'][0]['cross_voice'] = True
        training.write_json(training.project_path(self.project) / 'profile.json', data)
        training.approve(self.project, 'candidate', True)
        self.assertEqual(training.read_project(self.project)['active']['id'], 'candidate')

    def test_retention_preserves_approved_and_last_three(self):
        experiment = training.experiment(self.project)
        experiment.mkdir(parents=True)
        data = training.read_project(self.project)
        for number in range(5):
            model = experiment / f'lab_{self.project}_{number}e.pth'
            model.touch()
            data['candidates'].append({'id': str(number), 'epoch': number, 'model': str(model), 'approved': number == 0})
        training.write_json(training.project_path(self.project) / 'profile.json', data)
        training.prune_candidates(self.project)
        self.assertEqual([item['id'] for item in training.read_project(self.project)['candidates']], ['0', '2', '3', '4'])
        self.assertTrue(Path(data['candidates'][0]['model']).exists())
        self.assertFalse(Path(data['candidates'][1]['model']).exists())

    def test_direct_save_is_independent_of_validation(self):
        experiment = training.experiment(self.project)
        experiment.mkdir(parents=True)
        model = experiment / f'lab_{self.project}_25e_100s.pth'
        model.write_bytes(b'test-model')
        index = training.project_path(self.project) / 'test.index'
        index.write_bytes(b'test-index')
        data = training.read_project(self.project)
        data['candidates'] = [{'id': 'candidate', 'epoch': 25, 'model': str(model),
                               'index': str(index), 'tested': False, 'approved': False}]
        training.write_json(training.project_path(self.project) / 'profile.json', data)
        with self.assertRaisesRegex(ValueError, '勾选'):
            training.save_without_validation(self.project, 'candidate', False)
        training.save_without_validation(self.project, 'candidate', True)
        saved = training.read_project(self.project)
        self.assertTrue(saved['active']['validation_bypassed'])
        self.assertFalse(saved['active']['approved'])
        self.assertTrue(saved['candidates'][0]['pinned'])
        self.assertEqual(Path(saved['active']['model']).read_bytes(), model.read_bytes())
        self.assertEqual(Path(saved['active']['index']).read_bytes(), index.read_bytes())
        self.assertNotEqual(saved['active']['model'], str(model))

    def test_progress_registration_and_stop_request(self):
        experiment = training.experiment(self.project)
        experiment.mkdir(parents=True)
        model = experiment / f'lab_{self.project}_1e_10s.pth'
        model.write_bytes(b'complete-model')
        data = training.read_project(self.project)
        data.update(status='训练中', training_index='index')
        training.write_json(training.project_path(self.project) / 'profile.json', data)
        training.write_json(experiment / 'lab-progress.json', {'epoch': 1, 'model': str(model)})
        training.sync_saved_progress(self.project)
        training.sync_saved_progress(self.project)
        saved = training.read_project(self.project)
        self.assertEqual(saved['last_epoch'], 1)
        self.assertEqual(len(saved['candidates']), 1)
        training.request_save_stop(self.project)
        self.assertTrue((experiment / 'lab-save-stop.request').exists())

    def test_saved_version_is_not_pruned(self):
        experiment = training.experiment(self.project)
        experiment.mkdir(parents=True)
        data = training.read_project(self.project)
        for number in range(5):
            model = experiment / f'lab_{self.project}_{number}e.pth'
            model.write_bytes(b'weights')
            data['candidates'].append({'id': str(number), 'epoch': number, 'model': str(model),
                                       'pinned': number == 0, 'approved': False})
        data['active'] = data['candidates'][1]
        training.write_json(training.project_path(self.project) / 'profile.json', data)
        training.prune_candidates(self.project)
        self.assertEqual(len(training.read_project(self.project)['candidates']), 5)

    def test_backend_hook_rejects_changed_source(self):
        with self.assertRaisesRegex(RuntimeError, 'checkpoint hooks'):
            adapt_source('print("unsupported")')

    def test_resume_rejects_partial_checkpoint_pair(self):
        experiment = training.experiment(self.project)
        experiment.mkdir(parents=True)
        (experiment / 'G_2333333.pth').write_bytes(b'incomplete')
        with self.assertRaisesRegex(ValueError, '不完整'):
            training.validate_resume(self.project)

    def test_saved_voice_wins_over_stale_reference(self):
        self.assertEqual(resolve_source('old-reference.wav', 'rvc:' + self.project),
                         (True, None, 'rvc:' + self.project))
        self.assertEqual(resolve_source('old-reference.wav', 'rvc:' + self.project, '声线库'),
                         (True, None, 'rvc:' + self.project))

    def test_explicit_reference_mode_ignores_selected_model(self):
        self.assertEqual(resolve_source('reference.wav', 'rvc:' + self.project, '参考音频'),
                         (False, 'reference.wav', None))
        with self.assertRaisesRegex(ValueError, '上传参考'):
            resolve_source(None, 'rvc:' + self.project, '参考音频')
        with self.assertRaisesRegex(ValueError, '选择翻唱声线'):
            resolve_source('reference.wav', None, '声线库')

    def test_restore_skips_internal_validation_audio(self):
        with patch.object(exports.lab_env, 'ROOT', self.root):
            real = self.root / 'outputs/real/cover.wav'
            internal = self.root / 'outputs/internal/cover.wav'
            for path in (real, internal):
                path.parent.mkdir(parents=True)
                path.write_bytes(self.source.read_bytes())
            os.utime(real, (1, 1))
            (internal.parent / 'settings.json').write_text(json.dumps({'validation_only': True}), encoding='utf-8')
            self.assertEqual(exports.restore_latest(), (str(real), str(real)))

    def test_bad_audio_has_readable_error(self):
        bad = self.root / 'not-audio.txt'
        bad.write_text('not audio')
        with self.assertRaisesRegex(ValueError, '无法读取音频'):
            decode(bad, self.root / 'bad.wav')

    def test_download_is_attachment_and_rejects_traversal(self):
        exports.EXPORTS.mkdir()
        target = exports.EXPORTS / 'AI-cover-0123456789abcdef.wav'
        target.write_bytes(self.source.read_bytes())
        client = TestClient(exports.create_server())
        for method in ('get', 'head'):
            response = getattr(client, method)('/download/' + target.name)
            self.assertEqual(response.status_code, 200)
            self.assertIn('attachment;', response.headers['content-disposition'])
        response = client.get('/download/' + target.name)
        self.assertEqual(response.content, target.read_bytes())
        for filename in ('secret.wav', '..%2Fsecret.wav', 'AI-cover-0123456789abcdef.mp3'):
            self.assertEqual(client.get('/download/' + filename).status_code, 404)


if __name__ == '__main__':
    unittest.main()
