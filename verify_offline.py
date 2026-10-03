"""Run local runtime checks with synthetic audio, not private recordings."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def run(command, cwd):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=600)
    print(result.stdout, flush=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-5000:])
    return result.stdout


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--gpu', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    python = root / 'runtime/python/python.exe'
    os.environ['PYTHONUTF8'] = '1'
    os.environ['PYTHONNOUSERSITE'] = '1'
    os.environ['PYTHONHOME'] = str(python.parent)
    os.environ['PYTHONPATH'] = str(root)
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    run([str(python), '-c',
         'import sys, pathlib, torch, faiss, gradio, soundfile; '
         'assert pathlib.Path(sys.prefix).resolve()==pathlib.Path(sys.executable).resolve().parent; '
         'print(sys.executable,torch.__version__,torch.cuda.is_available(),faiss.__version__,gradio.__version__)'], root)
    run([str(python), '-B', '-m', 'unittest', 'discover', '-v'], root)
    if args.gpu:
        run([str(python), str(root / 'rvc_worker.py'), 'check'], root)
        run([str(python), str(root / 'worker.py'), 'check'], root)
        fixture = root / 'temp/offline-verification/input/synthetic.wav'
        output = fixture.parent.parent / 'converted.wav'
        fixture.parent.mkdir(parents=True, exist_ok=True)
        run([str(python), '-c',
             'import numpy as np,soundfile as sf; '
             't=np.arange(44100*4)/44100; '
             'x=sum(np.sin(2*np.pi*220*k*t)/k for k in range(1,9))*0.1; '
             f'sf.write({str(fixture)!r},x,44100)'], root)
        profile = root / 'training/3cccd738abed'
        conversion = run([str(python), str(root / 'rvc_worker.py'), 'convert', '--input', str(fixture),
             '--output', str(output), '--model', str(profile / 'saved/voice-25.pth'),
             '--index', str(profile / 'saved/voice.index')], root)
        index_loaded = False
        for line in conversion.splitlines():
            try:
                report = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(report, dict) and report.get('voice_index') == 'loaded':
                index_loaded = True
        assert index_loaded, 'Voice index was not used in GPU conversion'
        run([str(python), '-c',
             f'import soundfile as sf,numpy as np; x,sr=sf.read({str(output)!r}); '
             'assert sr==44100 and len(x)>sr*3 and np.isfinite(x).all(); '
             'assert np.sqrt(np.mean(x*x))>1e-5; print("inference audio valid",len(x)/sr)'], root)
        separated = fixture.parent.parent / 'separated'
        run([str(python), str(root / 'worker.py'), 'separate', '--input', str(fixture.parent),
             '--output', str(separated)], root)
        run([str(python), '-c',
             'from pathlib import Path; import numpy as np,soundfile as sf; '
             f'files=list(Path({str(separated)!r}).rglob("*.wav")); '
             'assert len(files)==3,files; '
             'assert all(np.isfinite(sf.read(f)[0]).all() and sf.info(f).duration>3 for f in files); '
             'print("three stems valid",[f.name for f in files])'], root)
    print(json.dumps({'offline_checks': 'passed', 'gpu': args.gpu}), flush=True)
