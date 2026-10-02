import lab_env
import faulthandler
faulthandler.enable()
import argparse
import json
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['check', 'convert'])
    parser.add_argument('--input')
    parser.add_argument('--output')
    parser.add_argument('--model')
    parser.add_argument('--index', default='')
    parser.add_argument('--pitch', type=int, default=0)
    args = parser.parse_args()
    repo = lab_env.ROOT / 'external' / 'Applio'
    os.chdir(repo)
    sys.path.insert(0, str(repo))
    import torch
    torch.set_num_threads(4)
    import faiss
    faiss.omp_set_num_threads(1)
    from rvc.infer.infer import VoiceConverter
    if args.action == 'check':
        from rvc.train import losses
        import faiss
        assert torch.cuda.is_available(), 'CUDA unavailable'
        print(json.dumps({'torch': torch.__version__, 'gpu': torch.cuda.get_device_name(0), 'faiss': faiss.__version__}))
        return
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    converter = VoiceConverter()
    converter.convert_audio(args.input, str(output), args.model, args.index,
                            pitch=args.pitch, index_rate=0.5, protect=0.33,
                            f0_method='rmvpe', volume_envelope=1.0,
                            resample_sr=0, clean_audio=False, f0_autotune=False)
    from audio_workflow import validate, decode
    import soundfile as sf
    # Preserve the model's native rate, then actually resample; changing only
    # Applio's output header would speed up a 40k model at 44.1k.
    if sf.info(output).samplerate != 44100:
        temporary = output.with_name(output.stem + '-resampled.wav')
        decode(output, temporary)
        os.replace(temporary, output)
    stats = validate(output)
    if stats['rms'] < 1e-5:
        raise RuntimeError('RVC output is silent')
    print(json.dumps(stats), flush=True)


if __name__ == '__main__':
    main()
