import json
import os
import sys
from pathlib import Path


def adapt_source(source):
    # Fail closed if the pinned backend's epoch boundary ever changes.
    start = '    # Save checkpoint\n'
    finish = '        if done:\n            # Clean-up process IDs from config.json\n'
    if source.count(start) != 1 or source.count(finish) != 1:
        raise RuntimeError('Unsupported training backend: checkpoint hooks not found')
    source = source.replace(start, '''    # Save checkpoint
    if os.path.exists(os.path.join(experiment_dir, "lab-save-stop.request")):
        custom_total_epoch = epoch
''', 1)
    source = source.replace(finish, '''        if model_add:
            saved_model = model_add[-1]
            if not os.path.isfile(saved_model) or os.path.getsize(saved_model) == 0:
                raise RuntimeError("Inference model was not saved")
            progress = os.path.join(experiment_dir, "lab-progress.json")
            with open(progress + ".tmp", "w", encoding="utf-8") as stream:
                json.dump({"epoch": epoch, "step": global_step, "model": saved_model}, stream)
            os.replace(progress + ".tmp", progress)

        if done:
            # Clean-up process IDs from config.json
''', 1)
    anchor = 'from rvc.train.process.extract_model import extract_model\n'
    if source.count(anchor) != 1:
        raise RuntimeError('Unsupported training backend: save helper not found')
    source = source.replace(anchor, anchor + '''
_backend_save_checkpoint = save_checkpoint
def save_checkpoint(model, optimizer, learning_rate, iteration, checkpoint_path, scaler):
    temporary = checkpoint_path + ".tmp"
    _backend_save_checkpoint(model, optimizer, learning_rate, iteration, temporary, scaler)
    os.replace(temporary, checkpoint_path)
''', 1)
    return source


if __name__ in ('__main__', '__mp_main__'):
    backend = Path(__file__).resolve().parent / 'external/Applio/rvc/train/train.py'
    sys.path.insert(0, str(backend.parent))
    source = adapt_source(backend.read_text(encoding='utf-8'))
    # Keep the upstream main-module identity for Windows multiprocessing spawn.
    exec(compile(source, str(backend), 'exec'), globals())
