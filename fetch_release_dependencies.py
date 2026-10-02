"""Fetch pinned redistribution dependencies, verifying the published checksums."""
import argparse
import hashlib
import time
from pathlib import Path

import requests

FFMPEG_URL = ('https://github.com/BtbN/FFmpeg-Builds/releases/download/'
              'autobuild-2026-10-01-13-06/ffmpeg-n9.0.2-22-g46d8f462ee-win64-lgpl-shared-9.0.zip')
FFMPEG_SHA = '2a41605c6c28455c7029e5057f77cda18838203fa09d40bed6e6cac14200e1f5'


def download(url, path, sha):
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == sha:
        return
    temporary = path.with_suffix(path.suffix + '.download')
    for attempt in range(3):
        try:
            hasher = hashlib.sha256()
            with requests.get(url, stream=True, timeout=(15, 90)) as response:
                response.raise_for_status()
                with temporary.open('wb') as stream:
                    for chunk in response.iter_content(1024 * 1024):
                        stream.write(chunk)
                        hasher.update(chunk)
            if hasher.hexdigest() != sha:
                raise RuntimeError(f'Checksum mismatch: {path.name}')
            temporary.replace(path)
            return
        except requests.RequestException as exc:
            print(f'{path.name}: attempt {attempt + 1}: {type(exc).__name__}', flush=True)
            if attempt == 2:
                raise
            time.sleep(2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    print('Also obtain spotify/pedalboard v0.9.17 with all pinned submodules for corresponding source.', flush=True)
    download(FFMPEG_URL, args.output / 'ffmpeg-lgpl.zip', FFMPEG_SHA)
    print('FFmpeg downloaded and verified', flush=True)
