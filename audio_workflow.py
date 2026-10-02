import lab_env
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import soundfile as sf

FFMPEG = Path(imageio_ffmpeg.get_ffmpeg_exe())
shim = lab_env.ROOT / 'runtime' / 'ffmpeg.exe'
if not shim.exists():
    shim.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(FFMPEG, shim)
    except OSError:
        shutil.copy2(FFMPEG, shim)

def decode(source, target, start=0, duration=0, mono=False, sample_rate=44100, codec='pcm_f32le'):
    command = [str(FFMPEG), '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(start), '-i', str(source)]
    if duration > 0:
        command += ['-t', str(duration)]
    command += ['-vn', '-ac', '1' if mono else '2', '-ar', str(sample_rate), '-c:a', codec, str(target)]
    result = subprocess.run(command, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        detail = result.stderr.decode('utf-8', errors='replace')[-1200:]
        raise ValueError(f'无法读取音频：{Path(source).name}。请确认文件含有可解码的音轨，且不是加密音乐或损坏文件。\n{detail}')
    validate(target)

def validate(path):
    wave, sr = sf.read(path, always_2d=True)
    if len(wave) < sr / 2 or not np.isfinite(wave).all():
        raise RuntimeError(f'Invalid audio: {path}')
    peak = float(np.max(np.abs(wave)))
    rms = float(np.sqrt(np.mean(wave ** 2)))
    return {'seconds': len(wave) / sr, 'sr': sr, 'peak': peak, 'rms': rms}

def stage(action, output, input_path, reference=None, steps=50, pitch=0, stop=None):
    log = output / f'{action}.log'
    command = [sys.executable, '-u', str(lab_env.ROOT / 'worker.py'), action, '--input', str(input_path), '--output', str(output)]
    if reference:
        command += ['--reference', str(reference), '--steps', str(steps), '--pitch', str(pitch)]
    with log.open('w', encoding='utf-8') as stream:
        process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT, cwd=lab_env.REPO, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            while process.poll() is None:
                if stop and stop.is_set():
                    raise RuntimeError('任务已停止')
                time.sleep(0.5)
                yield log
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=15)
    if process.returncode:
        detail = log.read_text(encoding='utf-8', errors='replace')[-3500:]
        raise RuntimeError(f'{action} failed.\n{detail}')

def mix(vocal, instrumental, backing, target, vocal_gain=3, harmony_gain=-16):
    lead, sr = sf.read(vocal, always_2d=True, dtype='float32')
    lead = np.repeat(lead, 2, axis=1) if lead.shape[1] == 1 else lead[:, :2]
    tracks = [(lead, vocal_gain)]
    for path, gain in [(instrumental, -3), (backing, harmony_gain)]:
        if path and gain > -48:
            wave, rate = sf.read(path, always_2d=True, dtype='float32')
            if rate != sr:
                raise RuntimeError('Stem sample rates do not match')
            tracks.append((wave[:, :2], gain))
    # Anchor the mix to the original stem length; do not shorten the song
    # to a generated vocal that may be one hop shorter.
    frames = len(tracks[1][0]) if instrumental else len(lead)
    mixed = np.zeros((frames, 2), dtype='float32')
    for wave, gain in tracks:
        n = min(frames, len(wave))
        mixed[:n] += wave[:n] * 10 ** (gain / 20)
    peak = np.max(np.abs(mixed))
    if peak > 0.97:
        mixed *= 0.97 / peak
    sf.write(target, mixed, sr, subtype='PCM_24')
    return validate(target)

def create_job():
    folder = lab_env.ROOT / 'outputs' / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
    (folder / 'input').mkdir(parents=True)
    return folder
