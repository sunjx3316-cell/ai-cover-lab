import lab_env
import json
import os
from pathlib import Path
from huggingface_hub import hf_hub_download

APPLIO = lab_env.ROOT / 'external' / 'Applio'


def fetch(filename, relative):
    destination = APPLIO / relative
    if destination.is_file() and destination.stat().st_size > 0:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f'Downloading {filename}', flush=True)
    # Download directly into the engine folder; do not keep a second model copy.
    path = Path(hf_hub_download('IAHispano/Applio', filename, local_dir=str(destination.parent)))
    if path != destination:
        os.replace(path, destination)


def main():
    if not (APPLIO / 'rvc').is_dir():
        raise RuntimeError('请先运行 Setup.cmd 安装 RVC 训练后端')
    for name in ('f0G40k.pth', 'f0D40k.pth'):
        fetch('Resources/pretrained_v2/' + name, 'rvc/models/pretraineds/hifi-gan/' + name)
    for name in ('config.json', 'pytorch_model.bin'):
        fetch('Resources/embedders/contentvec/' + name, 'rvc/models/embedders/contentvec/' + name)
    predictor = APPLIO / 'rvc/models/predictors/rmvpe.pt'
    if not predictor.exists():
        candidates = list((lab_env.REPO / 'checkpoints').rglob('rmvpe.pt'))
        if candidates:
            predictor.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(candidates[0], predictor)
            except OSError:
                import shutil
                shutil.copy2(candidates[0], predictor)
        else:
            fetch('Resources/predictors/rmvpe.pt', 'rvc/models/predictors/rmvpe.pt')
    settings = APPLIO / 'assets/config.json'
    data = json.loads(settings.read_text(encoding='utf-8')) if settings.exists() else {}
    data['precision'] = 'fp16'
    settings.write_text(json.dumps(data, indent=2), encoding='utf-8')
    if not any((lab_env.REPO / 'checkpoints').rglob('campplus_cn_common.bin')):
        hf_hub_download('funasr/campplus', 'campplus_cn_common.bin', cache_dir=str(lab_env.REPO / 'checkpoints'))
    print('RVC 40k training assets ready.', flush=True)


if __name__ == '__main__':
    main()
