"""Create a personal offline backup without marking it redistribution-ready."""
import argparse
import hashlib
import json
import time
import zipfile
from pathlib import Path

from build_offline import AUDIO, VOICE


def package(root, target):
    root = root.resolve()
    if target.exists():
        raise FileExistsError(target)
    temporary = target.with_suffix('.zip.partial')
    manifest = json.loads((root / 'MANIFEST.json').read_text(encoding='utf-8'))
    allowed_voice = {f'training/{VOICE}/profile.json', f'training/{VOICE}/saved/voice-25.pth',
                     f'training/{VOICE}/saved/voice.index'}
    files = []
    for name, item in manifest.items():
        relative = Path(name)
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or relative.is_absolute():
            raise ValueError('Unsafe manifest path')
        if relative.parts[0] in {'temp', 'logs', 'outputs', 'exports', 'cache', 'voices'}:
            raise ValueError('Private or temporary data in manifest')
        if relative.suffix.lower() in AUDIO:
            raise ValueError('Audio recordings must not be included in the local backup')
        if relative.parts[0] == 'training' and relative.as_posix() not in allowed_voice:
            raise ValueError('Unexpected training data in manifest')
        if not path.is_file() or path.stat().st_size != item['bytes']:
            raise ValueError(f'File changed after validation: {name}')
        files.append((path, relative.as_posix(), item))
    total = sum(item[2]['bytes'] for item in files)
    done = 0
    last = time.monotonic()
    print(f'Packing {len(files)} files, {total / 1024**3:.2f} GiB', flush=True)
    with zipfile.ZipFile(temporary, 'x', zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
        for path, name, item in files:
            hasher = hashlib.sha256()
            size = 0
            with path.open('rb') as source, archive.open('AI-Cover-Lab/' + name, 'w', force_zip64=True) as output:
                for block in iter(lambda: source.read(4 * 1024 * 1024), b''):
                    hasher.update(block)
                    size += len(block)
                    output.write(block)
            if size != item['bytes'] or hasher.hexdigest() != item['sha256']:
                raise ValueError(f'File changed after validation: {name}')
            done += size
            if time.monotonic() - last > 15:
                print(f'Packed {done / total:.0%}: {name}', flush=True)
                last = time.monotonic()
        archive.write(root / 'MANIFEST.json', 'AI-Cover-Lab/MANIFEST.json')
        archive.write(Path(__file__).with_name('LOCAL_USE.md'), 'AI-Cover-Lab/LOCAL_USE.md')
        archive.write(Path(__file__).with_name('LOCAL_USE.txt'), 'AI-Cover-Lab/LOCAL_USE.txt')
    print('Verifying ZIP CRC...', flush=True)
    with zipfile.ZipFile(temporary) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f'ZIP verification failed: {bad}')
        assert 'AI-Cover-Lab/Start-Cover.cmd' in archive.namelist()
    hasher = hashlib.sha256()
    with temporary.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            hasher.update(block)
    temporary.rename(target)
    target.with_suffix('.zip.sha256').write_text(hasher.hexdigest() + '  ' + target.name + '\n', encoding='ascii')
    print(json.dumps({'archive': str(target), 'bytes': target.stat().st_size,
                      'sha256': hasher.hexdigest(), 'private_backup': True}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--target', type=Path, required=True)
    args = parser.parse_args()
    package(args.root, args.target)
