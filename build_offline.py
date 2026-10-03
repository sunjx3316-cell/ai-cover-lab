"""Build a relocatable runtime from an existing, tested installation.

Only tracked engine source and explicitly selected model assets are copied.
Immutable runtime files may be hard-linked locally; the ZIP is self-contained.
"""
import argparse
import ast
import base64
import csv
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from package_release import FILES

SOURCE = Path(__file__).resolve().parent
VERSION = '0.1.0-beta'
VOICE = '3cccd738abed'
REVISIONS = {'Applio': '55fe0b976a6990bb75261c32ccecf6bfca3198f1',
             'YingMusic-SVC': '4974a80c6044c4557059548409379f6365129f88'}
AUDIO = {'.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.mp4'}


def digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            hasher.update(block)
    return hasher.hexdigest()


def copy(source, target, link=False):
    if not source.is_file():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(target)
    if link:
        try:
            os.link(source, target)
            return
        except OSError:
            pass
    shutil.copy2(source, target)


def tree(source, target, link=False, runtime=False, base_python=False, skip=()):
    for file in sorted(source.rglob('*')):
        relative = file.relative_to(source)
        if any(relative.as_posix() == item or relative.as_posix().startswith(item + '/') for item in skip):
            continue
        if not file.is_file() or any(part in {'.git', '__pycache__', '.cache'} for part in relative.parts):
            continue
        if file.suffix in {'.pyc', '.pyo'}:
            continue
        if base_python and relative.parts[:2] == ('Lib', 'site-packages'):
            continue
        if runtime and file.suffix.lower() in AUDIO:
            continue
        if runtime and (file.name in {'_virtualenv.py', '_virtualenv.pth'} or
                        'imageio_ffmpeg/binaries' in relative.as_posix() and file.suffix == '.exe'):
            continue
        copy(file, target / relative, link)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def optional_effects_source(text):
    module = ast.parse(text)
    imports = [node for node in module.body if isinstance(node, ast.ImportFrom) and node.module == 'pedalboard']
    methods = [node for node in ast.walk(module) if isinstance(node, ast.FunctionDef) and node.name == 'post_process_audio']
    if len(imports) != 1 or len(methods) != 1:
        raise RuntimeError('Pinned Applio optional-effects source contract changed')
    lines = text.splitlines(keepends=True)
    imported = ''.join(lines[imports[0].lineno - 1:imports[0].end_lineno])
    insertion = methods[0].body[0].lineno - 1
    lazy = '        try:\n' + ''.join('            ' + line for line in imported.splitlines(keepends=True))
    lazy += ('        except ImportError as error:\n'
             '            raise RuntimeError("Optional Applio effects are not included in this offline build") from error\n')
    lines[insertion:insertion] = [lazy]
    del lines[imports[0].lineno - 1:imports[0].end_lineno]
    result = ''.join(lines)
    ast.parse(result)
    return result


def validate_corresponding_sources(sources):
    sources = sources.resolve()
    provenance = json.loads((sources / 'SOURCE-MANIFEST.json').read_text(encoding='utf-8-sig'))
    required = {
        'ffmpeg': [('archive', 'sha256'), ('build_recipe_archive', 'build_recipe_sha256'),
                   ('dependency_cache_archive', 'dependency_cache_expected_sha256'),
                   ('dependency_notices_archive', 'dependency_notices_sha256')],
        'pedalboard': [('archive', 'sha256')],
        'soxr': [('archive', 'sha256'), ('build_recipe_archive', 'build_recipe_sha256'),
                 ('binding_source_archive', 'binding_source_sha256')],
        'libsndfile': [('archive', 'sha256'), ('wrapper_source_archive', 'wrapper_source_sha256'),
                      ('dependency_source_archive', 'dependency_source_sha256')],
        'runtime': [('archive', 'sha256')],
    }
    for component, archives in required.items():
        entry = provenance.get(component, {})
        # The original pedalboard manifest predates explicit review statuses.
        if component != 'pedalboard' and entry.get('status') != 'complete':
            raise RuntimeError(f'{component} corresponding-source audit is incomplete')
        if component == 'pedalboard' and entry.get('status', 'complete') != 'complete':
            raise RuntimeError('pedalboard corresponding-source audit is incomplete')
        for name_key, hash_key in archives:
            name, expected = entry.get(name_key), entry.get(hash_key)
            if not isinstance(name, str) or not name or not isinstance(expected, str) or len(expected) != 64:
                raise RuntimeError(f'{component} source archive declaration is incomplete')
            path = (sources / name).resolve()
            if not path.is_relative_to(sources):
                raise RuntimeError(f'{component} source archive escapes the source folder')
            if not path.is_file() or digest(path) != expected:
                raise RuntimeError(f'{component} source archive checksum mismatch')
    return provenance


def install_native_overrides(site, target, sndfile, soxr_wheel, provenance):
    for component, path, key in [('libsndfile', sndfile, 'binary_sha256'),
                                  ('soxr', soxr_wheel, 'wheel_sha256')]:
        expected = provenance[component].get(key)
        if not path or not expected or digest(path) != expected:
            raise RuntimeError(f'{component} rebuilt binary checksum mismatch')
    with zipfile.ZipFile(soxr_wheel) as wheel:
        for entry in wheel.infolist():
            path = Path(entry.filename)
            if (path.is_absolute() or '\\' in entry.orig_filename or ':' in entry.orig_filename or
                    '..' in path.parts or not path.parts or
                    path.parts[0] not in {'soxr', 'soxr-1.1.0.dist-info'}):
                raise RuntimeError('Unsafe or unexpected soxr wheel entry')
        for entry in wheel.infolist():
            if entry.is_dir():
                continue
            path = target / entry.filename
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as output:
                output.write(wheel.read(entry))
    copy(sndfile, target / '_soundfile_data/libsndfile_64bit.dll')
    # RECORD must be fresh too: the original runtime can share hard-linked files.
    relative = 'soundfile-0.12.1.dist-info/RECORD'
    with (site / relative).open(newline='', encoding='utf-8') as original:
        rows = list(csv.reader(original))
    name = '_soundfile_data/libsndfile_64bit.dll'
    checksum = base64.urlsafe_b64encode(bytes.fromhex(digest(sndfile))).rstrip(b'=').decode('ascii')
    found = False
    for row in rows:
        if row[0] == name:
            row[1:] = ['sha256=' + checksum, str(sndfile.stat().st_size)]
            found = True
    if not found:
        raise RuntimeError('SoundFile RECORD does not identify its native library')
    (target / relative).parent.mkdir(parents=True, exist_ok=True)
    with (target / relative).open('x', newline='', encoding='utf-8') as record:
        csv.writer(record).writerows(rows)


def assemble(installation, output, git, ffmpeg=None, sources=None, local_only=False,
             sndfile=None, soxr_wheel=None):
    if not local_only:
        provenance = validate_corresponding_sources(sources)
        license_text = subprocess.check_output([str(ffmpeg / 'bin/ffmpeg.exe'), '-L'], text=True, stderr=subprocess.STDOUT)
        if 'GNU Lesser General Public License' not in license_text:
            raise RuntimeError('Expected an LGPL FFmpeg build')
    payload = output / 'AI-Cover-Lab'
    if payload.exists():
        raise FileExistsError('Use a fresh output folder; existing installs are never overwritten.')
    payload.mkdir(parents=True)
    for name in FILES:
        copy(SOURCE / name, payload / name)
    python = installation / 'runtime/python/cpython-3.10-windows-x86_64-none'
    tree(python, payload / 'runtime/python', link=True, runtime=True, base_python=True)
    site = installation / 'envs/ying/Lib/site-packages'
    replacements = ('soxr', 'soxr-1.1.0.dist-info', '_soundfile_data/libsndfile_64bit.dll',
                    'pedalboard', 'pedalboard_native', 'pedalboard-0.9.17.dist-info',
                    'pedalboard_native.cp310-win_amd64.pyd',
                    'soundfile-0.12.1.dist-info/RECORD') if not local_only else ()
    target_site = payload / 'runtime/python/Lib/site-packages'
    tree(site, target_site, link=True, runtime=True, skip=replacements)
    if not local_only:
        install_native_overrides(site, target_site, sndfile, soxr_wheel, provenance)
    # Engine files are immutable here; copy only git-tracked, non-audio files.
    for name, revision in REVISIONS.items():
        repo = installation / 'external' / name
        actual = subprocess.check_output([git, '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != revision:
            raise RuntimeError(f'{name} revision mismatch: {actual}')
        tracked = subprocess.check_output([git, '-C', str(repo), 'ls-files', '-z']).decode('utf-8').split('\0')
        for relative in filter(None, tracked):
            path = Path(relative)
            if path.suffix.lower() in AUDIO | {'.pyc', '.pyo'} or '__pycache__' in path.parts:
                continue
            target = payload / 'external' / name / path
            if not local_only and name == 'Applio' and path.as_posix() == 'rvc/infer/infer.py':
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(optional_effects_source((repo / path).read_text(encoding='utf-8')), encoding='utf-8')
            else:
                copy(repo / path, target)
    assets = ['rvc/models/embedders/contentvec/config.json',
              'rvc/models/embedders/contentvec/pytorch_model.bin',
              'rvc/models/predictors/rmvpe.pt',
              'rvc/models/pretraineds/hifi-gan/f0G40k.pth',
              'rvc/models/pretraineds/hifi-gan/f0D40k.pth']
    for name in assets:
        copy(installation / 'external/Applio' / name, payload / 'external/Applio' / name, True)
    write_json(payload / 'external/Applio/assets/config.json', {'precision': 'fp16'})
    tree(installation / 'external/YingMusic-SVC/checkpoints',
         payload / 'external/YingMusic-SVC/checkpoints', link=True)
    for name in ['bs_roformer.ckpt', 'YingMusic-SVC-full.pt']:
        copy(installation / 'models' / name, payload / 'models' / name, True)
    saved = installation / 'training' / VOICE / 'saved/epoch-25'
    for original, name in [('voice-25.pth', 'voice-25.pth'), ('voice.index', 'voice.index')]:
        copy(saved / original, payload / 'training' / VOICE / 'saved' / name, True)
    if digest(payload / 'training' / VOICE / 'saved/voice-25.pth') != '91bc98037f32c3eca82dcbf4fb494a616a76fa99d43a3dc4c9a2ed97f5614a1b':
        raise RuntimeError('Bundled voice checksum mismatch')
    if digest(payload / 'training' / VOICE / 'saved/voice.index') != 'ac430a8b4c9653f91be510558c75c071a72551e3b96419090f61be08c279065c':
        raise RuntimeError('Bundled voice index checksum mismatch')
    write_json(payload / 'training' / VOICE / 'profile.json', {
        'id': VOICE, 'name': '凑企鹅', 'files': [], 'candidates': [], 'last_epoch': 25,
        'inference_only': True,
        'status': '已保存推理模型（未完整验收）',
        'active': {'id': 'bundled-25', 'epoch': 25, 'model': 'saved/voice-25.pth',
                   'index': 'saved/voice.index', 'approved': False,
                   'validation_bypassed': True, 'saved_by_user': True}})
    # Use a separately audited LGPL shared build, not imageio's GPL static exe.
    if local_only:
        copy(installation / 'runtime/ffmpeg.exe', payload / 'runtime/ffmpeg.exe', True)
    else:
        tree(ffmpeg / 'bin', payload / 'runtime')
        for item in ffmpeg.iterdir():
            if item.name != 'bin' and item.is_dir():
                tree(item, payload / 'LICENSES/FFmpeg-distribution' / item.name)
            elif item.is_file():
                copy(item, payload / 'LICENSES/FFmpeg-distribution' / item.name)
        tree(sources, payload / 'LICENSES/corresponding-source')
    write_json(payload / 'DEPENDENCIES.json', sorted([
        {'name': dist.metadata.get('Name'), 'version': dist.version,
         'license': dist.metadata.get('License-Expression') or dist.metadata.get('License', '')[:200],
         'license_files': list(dist.metadata.get_all('License-File') or [])}
        for dist in importlib.metadata.distributions(path=[str(target_site)])], key=lambda item: (item['name'] or '').lower()))
    write_json(payload / 'BUILD.json', {'version': VERSION, 'upstream_revisions': REVISIONS,
                                      'platform': 'Windows-x86_64', 'torch': '2.4.0+cu124',
                                      'voice_epoch': 25, 'includes_raw_audio': False,
                                      'optional_applio_effects': 'not bundled; lazy import patch' if not local_only else 'upstream',
                                      'redistribution_ready': not local_only})
    files = list(payload.rglob('*'))
    media = [str(file.relative_to(payload)) for file in files if file.is_file() and file.suffix.lower() in AUDIO]
    if media:
        raise RuntimeError(f'Unexpected audio/video in release: {media[:10]}')
    write_json(payload / 'MANIFEST.json', {
        file.relative_to(payload).as_posix(): {'bytes': file.stat().st_size, 'sha256': digest(file)}
        for file in files if file.is_file()})
    print(json.dumps({'payload': str(payload), 'files': sum(file.is_file() for file in files)}, ensure_ascii=False), flush=True)
    return payload


def archive(payload, destination, part_mib=900):
    build = json.loads((payload / 'BUILD.json').read_text(encoding='utf-8'))
    if not build.get('redistribution_ready'):
        raise RuntimeError('Local test bundle: redistribution dependencies have not been cleared.')
    target = destination / 'AI-Cover-Lab-Windows-offline.zip'
    if target.exists():
        raise FileExistsError(target)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as package:
        for number, file in enumerate(sorted(payload.rglob('*'))):
            relative = file.relative_to(payload)
            if not file.is_file() or '__pycache__' in relative.parts or file.suffix in {'.pyc', '.pyo'}:
                continue
            if relative.parts[0] in {'temp', 'logs', 'outputs', 'exports', 'cache'}:
                continue
            allowed_training = {f'training/{VOICE}/profile.json', f'training/{VOICE}/saved/voice-25.pth',
                                f'training/{VOICE}/saved/voice.index'}
            if relative.parts[0] == 'voices' or (relative.parts[0] == 'training' and relative.as_posix() not in allowed_training):
                raise RuntimeError(f'Unexpected private data in release: {relative}')
            package.write(file, 'AI-Cover-Lab/' + relative.as_posix())
            if number % 2000 == 0:
                print(f'Packing: {relative}', flush=True)
    print('Verifying public archive ZIP CRC...', flush=True)
    with zipfile.ZipFile(target) as package:
        failed = package.testzip()
        if failed:
            raise RuntimeError(f'Public archive CRC mismatch: {failed}')
    parts = []
    with target.open('rb') as stream:
        number = 1
        while True:
            block = stream.read(min(part_mib * 1024 * 1024, 4 * 1024 * 1024))
            if not block:
                break
            part = destination / f'{target.name}.part{number:02d}'
            if part.exists():
                raise FileExistsError(part)
            with part.open('xb') as output:
                remaining = part_mib * 1024 * 1024
                while block:
                    output.write(block)
                    remaining -= len(block)
                    if not remaining:
                        break
                    block = stream.read(min(remaining, 4 * 1024 * 1024))
            parts.append({'name': part.name, 'bytes': part.stat().st_size, 'sha256': digest(part)})
            number += 1
    write_json(destination / 'offline-manifest.json', {'version': VERSION, 'archive': target.name,
        'bytes': target.stat().st_size, 'sha256': digest(target),
        'uncompressed_bytes': sum(file.stat().st_size for file in payload.rglob('*') if file.is_file()), 'parts': parts})
    for name in ['install-offline.ps1', 'Install-Offline.cmd']:
        copy(SOURCE / name, destination / name)
    print(json.dumps({'archive': str(target), 'bytes': target.stat().st_size, 'parts': len(parts)}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--installation', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--git', default='git')
    parser.add_argument('--ffmpeg', type=Path)
    parser.add_argument('--sources', type=Path)
    parser.add_argument('--sndfile', type=Path, help='Audited rebuilt shared libsndfile DLL')
    parser.add_argument('--soxr-wheel', type=Path, help='Audited rebuilt soxr wheel')
    parser.add_argument('--archive-only', action='store_true')
    parser.add_argument('--local-only', action='store_true', help='Personal relocation test only; cannot create distribution archive')
    args = parser.parse_args()
    if not args.archive_only:
        if not args.local_only and (not args.ffmpeg or not args.sources or not any(args.sources.iterdir()) or
                                   not args.sndfile or not args.soxr_wheel):
            parser.error('Audited FFmpeg, corresponding sources, libsndfile and soxr wheel are required')
        assemble(args.installation.resolve(), args.output.resolve(), args.git,
                 args.ffmpeg.resolve() if args.ffmpeg else None,
                 args.sources.resolve() if args.sources else None, args.local_only,
                 args.sndfile.resolve() if args.sndfile else None,
                 args.soxr_wheel.resolve() if args.soxr_wheel else None)
    else:
        archive(args.output.resolve() / 'AI-Cover-Lab', args.output.resolve())
