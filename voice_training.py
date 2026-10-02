import lab_env
import hashlib
import json
import re
import shutil
import sys
import time
import uuid
from pathlib import Path

from audio_workflow import decode, validate
from process_runner import run_process

ROOT = lab_env.ROOT / 'training'
APPLIO = lab_env.ROOT / 'external' / 'Applio'


def write_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def project_path(project_id):
    if not re.fullmatch(r'[0-9a-f]{12}', project_id or ''):
        raise ValueError('请先创建或选择训练声线')
    folder = ROOT / project_id
    if not (folder / 'profile.json').exists():
        raise ValueError('训练声线不存在')
    return folder


def read_project(project_id):
    return json.loads((project_path(project_id) / 'profile.json').read_text(encoding='utf-8-sig'))


def choices(approved_only=False):
    result = []
    for file in sorted(ROOT.glob('*/profile.json')):
        data = json.loads(file.read_text(encoding='utf-8-sig'))
        if data.get('demo'):
            continue
        if not approved_only or data.get('active'):
            result.append((data['name'], data['id']))
    return result


def create_project(name):
    name = (name or '').strip()
    if not name:
        raise ValueError('请填写声线名称')
    project_id = uuid.uuid4().hex[:12]
    folder = ROOT / project_id
    for directory in ('train', 'holdout', 'probes', 'reports', 'logs'):
        (folder / directory).mkdir(parents=True, exist_ok=True)
    write_json(folder / 'profile.json', {'id': project_id, 'name': name, 'files': [], 'candidates': [],
                                       'last_epoch': 0, 'active': None, 'status': '素材待添加'})
    return project_id


def add_materials(project_id, train, holdout, probes):
    folder = project_path(project_id)
    data = read_project(project_id)
    added = []
    duplicate = 0
    for split, files in [('train', train), ('holdout', holdout), ('probes', probes)]:
        for file in files or []:
            target = folder / split / (uuid.uuid4().hex + '.wav')
            decode(file, target, mono=True, sample_rate=40000, codec='pcm_s16le')
            stats = validate(target)
            if stats['seconds'] < 3 or stats['rms'] < 1e-5:
                target.unlink()
                raise ValueError(f'{Path(file).name} 太短或接近静音，请使用至少 3 秒的清晰人声')
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            previous = next((item for item in data['files'] if item['sha256'] == digest), None)
            if previous:
                target.unlink()
                if previous['split'] != split:
                    raise ValueError(f'{Path(file).name} 与 {previous["split"]} 素材重复，训练和验证不能使用同一录音')
                duplicate += 1
                continue
            entry = {'name': Path(file).name, 'path': str(target.relative_to(folder)), 'split': split,
                     'sha256': digest, 'seconds': stats['seconds'], 'peak': stats['peak']}
            data['files'].append(entry)
            added.append(entry)
            # Persist each validated source so a later invalid file cannot lose earlier additions.
            write_json(folder / 'profile.json', data)
    if added:
        data['status'] = '素材已更新，待训练'
        write_json(folder / 'profile.json', data)
    return f'已添加 {len(added)} 个素材，跳过 {duplicate} 个重复文件\n' + summary(project_id)


def summary(project_id):
    data = read_project(project_id)
    lines = [f'声线：{data["name"]} · {data["status"]}', f'已训练：{data["last_epoch"]} 轮']
    for split, label in [('train', '训练素材'), ('holdout', '目标声线验证'), ('probes', '跨声线测试')]:
        files = [item for item in data['files'] if item['split'] == split]
        lines.append(f'{label}：{len(files)} 个 · {sum(item["seconds"] for item in files) / 60:.1f} 分钟')
    if sum(item['seconds'] for item in data['files'] if item['split'] == 'train') < 600:
        lines.append('训练素材不足 10 分钟，可试训，但不保证声线覆盖和泛化效果。')
    if data.get('active'):
        lines.append(f'已入库：第 {data["active"]["epoch"]} 轮版本')
        if data['active'].get('validation_bypassed'):
            lines.append('此版本为手动保存，未通过完整质量验收。')
    return '\n'.join(lines)


def experiment(project_id):
    return APPLIO / 'logs' / ('lab_' + project_id)


def run_stage(command, project_id, title, stop, monitor=None):
    log = project_path(project_id) / 'logs' / (str(time.time_ns()) + '-' + title + '.log')
    started = time.monotonic()
    for detail in run_process(command, log, APPLIO, stop):
        if monitor:
            monitor()
        yield f'{title} · {int(time.monotonic() - started)} 秒\n{detail}'


def rvc_command(source, target, model, index='', pitch=0):
    return [sys.executable, '-u', lab_env.ROOT / 'rvc_worker.py', 'convert', '--input', source,
            '--output', target, '--model', model, '--index', index, '--pitch', str(pitch)]


def candidate(project_id, candidate_id):
    data = read_project(project_id)
    item = next((item for item in data['candidates'] if item['id'] == candidate_id), None)
    if not item:
        raise ValueError('请先选择训练版本')
    return item

def prune_candidates(project_id):
    data = read_project(project_id)
    keep = {item['id'] for item in data['candidates'][-3:]} | {item['id'] for item in data['candidates'] if item.get('approved') or item.get('pinned')}
    if data.get('active'):
        keep.add(data['active']['id'])
    for item in data['candidates']:
        if item['id'] not in keep:
            path = Path(item['model']).resolve()
            if path.parent == experiment(project_id).resolve() and path.name.startswith('lab_' + project_id + '_'):
                path.unlink(missing_ok=True)
    data['candidates'] = [item for item in data['candidates'] if item['id'] in keep]
    write_json(project_path(project_id) / 'profile.json', data)


def request_save_stop(project_id):
    data = read_project(project_id)
    if data['status'] != '训练中':
        return '当前没有运行中的训练，已保存的版本可直接选择。'
    experiment(project_id).mkdir(parents=True, exist_ok=True)
    (experiment(project_id) / 'lab-save-stop.request').write_text('save after epoch', encoding='ascii')
    return '已请求保存后停止：等待当前轮完成，保存模型与续训检查点后停止；每轮可能需要数分钟。'


def sync_saved_progress(project_id):
    data = read_project(project_id)
    progress = experiment(project_id) / 'lab-progress.json'
    if not progress.exists() or not data.get('training_index'):
        return
    saved = json.loads(progress.read_text(encoding='utf-8'))
    model = Path(saved['model']).resolve()
    if model.parent != experiment(project_id).resolve() or not model.name.startswith('lab_' + project_id + '_'):
        raise ValueError('Invalid saved training model path')
    if not model.is_file() or not model.stat().st_size:
        raise ValueError('保存的训练模型不存在或为空')
    if saved['epoch'] <= data['last_epoch']:
        return
    data['last_epoch'] = saved['epoch']
    data['candidates'].append({'id': uuid.uuid4().hex[:12], 'epoch': saved['epoch'],
                              'model': str(model), 'index': data['training_index'],
                              'tested': False, 'approved': False})
    write_json(project_path(project_id) / 'profile.json', data)
    prune_candidates(project_id)


def validate_resume(project_id):
    import torch
    data = read_project(project_id)
    paths = [experiment(project_id) / f'{prefix}_2333333.pth' for prefix in ('G', 'D')]
    if not any(path.exists() for path in paths) and not data['last_epoch']:
        return
    if not all(path.is_file() for path in paths):
        raise ValueError('续训检查点不完整，不能继续；已保存的推理模型仍可使用')
    epochs = [torch.load(path, map_location='cpu', mmap=True, weights_only=True)['iteration'] for path in paths]
    if epochs != [data['last_epoch'], data['last_epoch']]:
        raise ValueError('续训检查点轮数不一致，已保留文件，请先检查；不会自动重头训练')


def train_voice(project_id, epochs, interval, batch_size, stop, checkpointing=True):
    folder = project_path(project_id)
    data = read_project(project_id)
    if not any(item['split'] == 'train' for item in data['files']):
        raise ValueError('请先添加训练素材')
    if not (APPLIO / 'rvc/train/train.py').exists():
        raise ValueError('训练后端未安装，请运行 Setup.cmd')
    validate_resume(project_id)
    epochs, interval, batch_size = int(epochs), int(interval), int(batch_size)
    if not 1 <= epochs <= 1000 or not 1 <= interval <= 100 or not 1 <= batch_size <= 4:
        raise ValueError('训练参数超出范围')
    data['status'] = '训练中'
    write_json(folder / 'profile.json', data)
    save_stop = experiment(project_id) / 'lab-save-stop.request'
    save_stop.unlink(missing_ok=True)
    name = 'lab_' + project_id
    try:
        yield from run_stage([sys.executable, '-u', lab_env.ROOT / 'prepare_rvc.py'], project_id, '准备训练权重', stop)
        preprocess = APPLIO / 'rvc/train/preprocess/preprocess.py'
        yield from run_stage([sys.executable, '-u', preprocess, experiment(project_id), folder / 'train',
                              40000, 4, 'Automatic', False, False, 0.7, 3.0, 0.3, 'none'], project_id, '切片与预处理', stop)
        extract = APPLIO / 'rvc/train/extract/extract.py'
        yield from run_stage([sys.executable, '-u', extract, experiment(project_id), 'rmvpe', 2, '0',
                              40000, 'contentvec', 'None', 0], project_id, '音高与声学特征', stop)
        filelist = experiment(project_id) / 'filelist.txt'
        if not filelist.exists() or len(filelist.read_text().splitlines()) < 6:
            raise ValueError('有效切片不足，至少需要 6 个可用片段，请补充素材')
        digest = hashlib.sha256(''.join(sorted(item['sha256'] for item in data['files'] if item['split'] == 'train')).encode()).hexdigest()[:16]
        index = folder / 'indexes' / (digest + '.index')
        if not index.exists():
            index.parent.mkdir(exist_ok=True)
            generated = experiment(project_id) / (name + '.index')
            if generated.exists():
                generated.unlink()
            yield from run_stage([sys.executable, '-u', APPLIO / 'rvc/train/process/extract_index.py',
                                  experiment(project_id), 'Auto'], project_id, '建立声线检索索引', stop)
            if not generated.exists():
                raise RuntimeError('声线检索索引未生成')
            generated.replace(index)
        data = read_project(project_id)
        data['training_index'] = str(index)
        write_json(folder / 'profile.json', data)
        end_epoch = data['last_epoch'] + epochs
        current = data['last_epoch']
        while current < end_epoch:
            if save_stop.exists():
                break
            target_epoch = min(current + interval, end_epoch)
            command = [sys.executable, '-u', lab_env.ROOT / 'train_rvc.py', name,
                       1, target_epoch,
                       APPLIO / 'rvc/models/pretraineds/hifi-gan/f0G40k.pth',
                       APPLIO / 'rvc/models/pretraineds/hifi-gan/f0D40k.pth',
                       '0', batch_size, 40000, True, True, False, False, 'HiFi-GAN', checkpointing]
            for message in run_stage(command, project_id, f'训练至第{target_epoch}轮', stop,
                                     lambda: sync_saved_progress(project_id)):
                saved_epoch = read_project(project_id)['last_epoch']
                yield f'本次目标：第 {end_epoch} 轮 · 已保存：第 {saved_epoch} 轮\n{message}'
            sync_saved_progress(project_id)
            data = read_project(project_id)
            if data['last_epoch'] <= current or (not save_stop.exists() and data['last_epoch'] != target_epoch):
                raise RuntimeError('训练没有产出当前版本，不能标记为成功，请查看训练日志')
            current = data['last_epoch']
            if save_stop.exists():
                break
            item = data['candidates'][-1]
            if any(file['split'] == 'holdout' for file in data['files']):
                yield from evaluate(project_id, item['id'], stop)
            prune_candidates(project_id)
        data = read_project(project_id)
        data['status'] = '已保存并暂停训练' if save_stop.exists() else '训练完成，模型已保存'
        write_json(folder / 'profile.json', data)
        yield summary(project_id)
    except Exception:
        sync_saved_progress(project_id)
        data = read_project(project_id)
        data['status'] = '任务已停止' if stop.is_set() else '训练失败，检查日志'
        write_json(folder / 'profile.json', data)
        raise


def save_without_validation(project_id, candidate_id, confirmed):
    if not confirmed:
        raise ValueError('请勾选确认跳过验收；保存模型不代表质量已经合格')
    folder = project_path(project_id)
    data = read_project(project_id)
    item = candidate(project_id, candidate_id)
    source = Path(item['model']).resolve()
    if source.parent != experiment(project_id).resolve() or not source.is_file() or not source.stat().st_size:
        raise ValueError('当前版本没有可保存的模型文件')
    destination = folder / 'saved' / item['id']
    destination.mkdir(parents=True, exist_ok=True)
    model = destination / 'voice.pth'
    shutil.copy2(source, model)
    if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(model.read_bytes()).digest():
        raise RuntimeError('模型备份校验失败')
    active = dict(item, model=str(model), validation_bypassed=True, saved_by_user=True)
    if item.get('index'):
        source_index = Path(item['index']).resolve()
        if not source_index.is_relative_to(folder.resolve()) or not source_index.is_file():
            raise ValueError('声线索引不存在')
        index = destination / 'voice.index'
        shutil.copy2(source_index, index)
        if hashlib.sha256(source_index.read_bytes()).digest() != hashlib.sha256(index.read_bytes()).digest():
            raise RuntimeError('索引备份校验失败')
        active['index'] = str(index)
    for entry in data['candidates']:
        if entry['id'] == candidate_id:
            entry['pinned'] = True
    data['active'] = active
    data['status'] = '已保存并加入声线库（跳过完整验收）'
    write_json(folder / 'profile.json', data)
    return summary(project_id)


def evaluate(project_id, candidate_id, stop):
    folder = project_path(project_id)
    data = read_project(project_id)
    item = candidate(project_id, candidate_id)
    report_dir = folder / 'reports' / candidate_id
    report_dir.mkdir(exist_ok=True)
    references = [folder / file['path'] for file in data['files'] if file['split'] == 'holdout'][:3]
    tests = [file for file in data['files'] if file['split'] in ('holdout', 'probes')]
    tests = [file for file in tests if file['split'] == 'holdout'][:2] + [file for file in tests if file['split'] == 'probes'][:3]
    records = []
    for number, file in enumerate(tests):
        source = report_dir / f'{number}-source.wav'
        converted = report_dir / f'{number}-converted.wav'
        decode(folder / file['path'], source, duration=12, mono=True)
        yield from run_stage(rvc_command(source, converted, item['model'], item.get('index', '')), project_id, f'验收试听{number + 1}', stop)
        records.append({'name': file['name'], 'split': file['split'], 'source': str(source), 'converted': str(converted)})
    manifest = report_dir / 'manifest.json'
    write_json(manifest, {'references': [str(file) for file in references], 'samples': records,
                          'model': item['model'], 'epoch': item['epoch']})
    yield from run_stage([sys.executable, '-u', lab_env.ROOT / 'evaluate_voice.py', manifest], project_id, '计算验收指标', stop)
    report = json.loads((report_dir / 'report.json').read_text(encoding='utf-8'))
    data = read_project(project_id)
    for entry in data['candidates']:
        if entry['id'] == candidate_id:
            entry.update({'tested': True, 'technical_pass': report['technical_pass'],
                          'cross_voice': any(sample['split'] == 'probes' for sample in records),
                          'report': str(report_dir / 'report.json')})
    write_json(folder / 'profile.json', data)
    yield f'第 {item["epoch"]} 轮验收试听已生成；请试听后决定入库。'


def approve(project_id, candidate_id, confirmed):
    if not confirmed:
        raise ValueError('请先试听并勾选验收确认')
    data = read_project(project_id)
    item = candidate(project_id, candidate_id)
    if not item.get('tested') or not item.get('technical_pass'):
        raise ValueError('当前版本尚未完成技术检测，或存在静音、时长异常等问题')
    if not item.get('cross_voice'):
        raise ValueError('请添加跨声线测试音频并重新验收，不能只凭目标声线自重建入库')
    data['active'] = dict(item, approved=True)
    for entry in data['candidates']:
        if entry['id'] == candidate_id:
            entry['approved'] = True
    data['status'] = '已验收入库'
    write_json(project_path(project_id) / 'profile.json', data)
    return summary(project_id)


def active_model(project_id):
    data = read_project(project_id)
    active = data.get('active')
    if not active:
        raise ValueError('该声线没有可用的已保存模型')

    def resolve(value):
        if not value:
            return ''
        path = Path(value)
        if not path.is_absolute():
            folder = project_path(project_id).resolve()
            path = (folder / path).resolve()
            if not path.is_relative_to(folder):
                raise ValueError('模型路径超出声线目录')
        if not path.is_file():
            raise ValueError('该声线的模型或索引文件不存在')
        return str(path)

    return resolve(active['model']), resolve(active.get('index', ''))
