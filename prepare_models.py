import lab_env
import argparse
import json
import shutil
import time
from pathlib import Path
from huggingface_hub import hf_hub_download, snapshot_download

root = lab_env.ROOT
repo = lab_env.REPO

def fetch(repo_id, filename, destination=None, cache_dir=None):
    if destination and destination.exists() and destination.stat().st_size > 0:
        return str(destination)
    print(f'Downloading {repo_id}/{filename}', flush=True)
    for attempt in range(4):
        try:
            path = hf_hub_download(repo_id, filename, cache_dir=cache_dir,
                                   local_dir=str(destination.parent) if destination else None)
            break
        except Exception as exc:
            if attempt == 3:
                raise
            print(f'Retrying download: {type(exc).__name__}', flush=True)
            time.sleep(2)
    if destination:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if Path(path).resolve() != destination.resolve():
            Path(path).replace(destination)
    return path

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--feature', choices=['all', 'separator', 'ying'], default='all')
    feature = parser.parse_args().feature
    if feature in ('all', 'separator'):
        fetch('GiantAILab/YingMusic-SVC', 'bs_roformer.ckpt', root / 'models' / 'bs_roformer.ckpt')
    if feature in ('all', 'ying'):
        fetch('GiantAILab/YingMusic-SVC', 'YingMusic-SVC-full.pt', root / 'models' / 'YingMusic-SVC-full.pt')
        fetch('lj1995/VoiceConversionWebUI', 'rmvpe.pt', cache_dir=str(repo / 'checkpoints'))
        fetch('funasr/campplus', 'campplus_cn_common.bin', cache_dir=str(repo / 'checkpoints'))
        for filename in ['config.json', 'model.safetensors', 'preprocessor_config.json', 'generation_config.json']:
            fetch('openai/whisper-small', filename, cache_dir=str(repo / 'checkpoints/hf_cache'))
        for filename in ['config.json', 'bigvgan_generator.pt']:
            fetch('nvidia/bigvgan_v2_44khz_128band_512x', filename, cache_dir=str(repo / 'checkpoints/hf_cache'))
    print('Selected model files ready.', flush=True)
