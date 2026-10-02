import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = ['app.py', 'lab_env.py', 'audio_workflow.py', 'worker.py', 'process_runner.py',
         'exports.py', 'voice_training.py', 'training_ui.py', 'voice_selection.py', 'rvc_worker.py', 'train_rvc.py', 'evaluate_voice.py',
         'prepare_rvc.py', 'prepare_models.py', 'setup.ps1', 'Setup.cmd', 'start.ps1', 'Start-Cover.cmd',
         'requirements-engine.txt', 'README.md', 'THIRD_PARTY.md', 'LICENSE', '.gitignore',
         'test_contracts.py', 'package_release.py', 'stop.ps1', 'Stop-Cover.cmd',
         'MODEL_CARD.md', 'PRIVACY.md', 'CONTRIBUTING.md', 'RELEASE_NOTES.md',
         'build_offline.py', 'install-offline.ps1', 'Install-Offline.cmd', 'fetch_release_dependencies.py',
         'verify_offline.py', 'test_offline_packaging.py', 'package_local.py', 'LOCAL_USE.md',
         'test_local_package.py', 'LOCAL_USE.txt']


def build():
    destination = ROOT / 'dist'
    destination.mkdir(exist_ok=True)
    target = destination / 'AI-Cover-Lab-source.zip'
    manifest = {}
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in FILES:
            source = ROOT / name
            data = source.read_bytes()
            archive.writestr('AI-Cover-Lab/' + name, data)
            manifest[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        archive.writestr('AI-Cover-Lab/MANIFEST.json', json.dumps(manifest, indent=2))
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert all(name.split('/')[1] in FILES + ['MANIFEST.json'] for name in archive.namelist())
    print(json.dumps({'package': str(target), 'bytes': target.stat().st_size, 'files': len(FILES)}))
    return target


if __name__ == '__main__':
    build()
