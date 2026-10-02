import lab_env
import json
import sys
from pathlib import Path

import librosa
import numpy as np
import torch
import torchaudio
from audio_workflow import validate


def main():
    manifest = Path(sys.argv[1])
    data = json.loads(manifest.read_text(encoding='utf-8'))
    sys.path.insert(0, str(lab_env.REPO))
    from modules.campplus.DTDNN import CAMPPlus
    checkpoint = next((lab_env.REPO / 'checkpoints').rglob('campplus_cn_common.bin'))
    torch.set_num_threads(4)
    model = CAMPPlus(feat_dim=80, embedding_size=192).eval()
    model.load_state_dict(torch.load(checkpoint, map_location='cpu', weights_only=True))

    def embedding(file):
        wave, _ = librosa.load(file, sr=16000, duration=12)
        features = torchaudio.compliance.kaldi.fbank(torch.from_numpy(wave).unsqueeze(0),
                                                   num_mel_bins=80, dither=0, sample_frequency=16000)
        features -= features.mean(dim=0, keepdim=True)
        with torch.inference_mode():
            value = model(features.unsqueeze(0)).numpy().ravel()
        return value / max(np.linalg.norm(value), 1e-8)

    references = [embedding(file) for file in data['references']]
    samples = []
    for item in data['samples']:
        original = validate(item['source'])
        converted = validate(item['converted'])
        wave, _ = librosa.load(item['converted'], sr=None)
        ratio = converted['seconds'] / original['seconds']
        clipping = float(np.mean(np.abs(wave) >= 0.999))
        similarity = float(np.mean([float(np.dot(embedding(item['converted']), ref)) for ref in references]))
        # These detect broken outputs, not whether a voice sounds convincing.
        technical = converted['rms'] >= 1e-5 and 0.95 <= ratio <= 1.05 and clipping < 0.001
        samples.append(dict(item, seconds=converted['seconds'], rms=converted['rms'],
                            clipping_ratio=clipping, duration_ratio=ratio,
                            speaker_cosine=similarity, technical_pass=technical))
    report = {'epoch': data['epoch'], 'model': data['model'], 'samples': samples,
              'technical_pass': bool(samples) and all(item['technical_pass'] for item in samples),
              'note': '声纹分数只用于同一批测试素材的版本对比，不是质量合格线。自然度、旋律、咬字和声线相似度需试听确认。'}
    (manifest.parent / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
