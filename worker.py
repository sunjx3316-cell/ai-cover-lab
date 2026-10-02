import lab_env
import argparse
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.chdir(lab_env.REPO)
sys.path.insert(0, str(lab_env.REPO))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['check', 'separate', 'convert'])
    parser.add_argument('--input')
    parser.add_argument('--reference')
    parser.add_argument('--output')
    parser.add_argument('--steps', type=int, default=50)
    parser.add_argument('--pitch', type=int, default=0)
    args = parser.parse_args()
    import torch
    torch.set_num_threads(4)
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA is unavailable; install the CUDA PyTorch build.')
    print(f'GPU: {torch.cuda.get_device_name(0)}; torch: {torch.__version__}', flush=True)
    if args.action == 'check':
        import my_inference
        from accom_separation.inference import proc_folder
        from utils.settings import get_model_from_config
        model, _ = get_model_from_config('bs_roformer', str(lab_env.REPO / 'accom_separation/ckpt/bs_roformer/config_bd_roformer.yaml'))
        print('SVC and separator imports OK; separator initialized.', flush=True)
        return
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.action == 'separate':
        import yaml
        from accom_separation.inference import proc_folder
        config_path = lab_env.REPO / 'accom_separation/ckpt/bs_roformer/config_bd_roformer.yaml'
        with config_path.open() as stream:
            config = yaml.load(stream, Loader=yaml.FullLoader)
        config['inference']['batch_size'] = 1
        local_config = output / 'separator-8gb.yaml'
        with local_config.open('w') as stream:
            yaml.dump(config, stream)
        proc_folder({
            'model_type': 'bs_roformer',
            'config_path': str(local_config),
            'start_check_point': str(lab_env.ROOT / 'models/bs_roformer.ckpt'),
            'input_folder': args.input,
            'store_dir': str(output),
            # This checkpoint already predicts all three stems. Subtraction
            # would overwrite its instrumental with instrumental plus harmony.
            'extract_instrumental': False,
            'extract_other': False,
            'device_ids': [0],
            'disable_detailed_pbar': False,
            'force_cpu': False,
            'flac_file': False,
            'use_tta': False,
        })
        return
    from my_inference import load_models_api, run_inference
    params = SimpleNamespace(
        source=args.input, target=args.reference,
        checkpoint=str(lab_env.ROOT / 'models/YingMusic-SVC-full.pt'),
        config=str(lab_env.REPO / 'configs/YingMusic-SVC.yml'),
        diffusion_steps=args.steps, fp16=True, f0_condition=True,
        semi_tone_shift=args.pitch, length_adjust=1.0,
        inference_cfg_rate=0.7, output=str(output), expname='converted',
    )
    torch.manual_seed(126)
    with torch.inference_mode():
        bundle = load_models_api(params, device=torch.device('cuda:0'))
        path = run_inference(params, bundle, device=torch.device('cuda:0'))
    print(json.dumps({'converted': path}), flush=True)

if __name__ == '__main__':
    main()
