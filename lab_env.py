import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT / 'external' / 'YingMusic-SVC'
for name, value in {
    'HF_HOME': ROOT / 'cache' / 'huggingface',
    'HF_HUB_CACHE': ROOT / 'cache' / 'huggingface' / 'hub',
    'TORCH_HOME': ROOT / 'cache' / 'torch',
    'TEMP': ROOT / 'temp',
    'TMP': ROOT / 'temp',
    'GRADIO_TEMP_DIR': ROOT / 'temp' / 'gradio',
    'MPLCONFIGDIR': ROOT / 'cache' / 'matplotlib',
    'NUMBA_CACHE_DIR': ROOT / 'cache' / 'numba',
}.items():
    Path(value).mkdir(parents=True, exist_ok=True)
    os.environ[name] = str(value)
os.environ['PYTHONUTF8'] = '1'
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
os.environ['HF_HUB_DISABLE_XET'] = '1'
os.environ['GRADIO_ANALYTICS_ENABLED'] = 'False'
os.environ['WANDB_MODE'] = 'disabled'
if (ROOT / 'runtime' / 'python' / 'python.exe').is_file():
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['IMAGEIO_FFMPEG_EXE'] = str(ROOT / 'runtime' / 'ffmpeg.exe')
