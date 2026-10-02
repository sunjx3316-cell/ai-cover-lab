import json
import threading
from pathlib import Path

import gradio as gr
import voice_training as training

STOP = threading.Event()


def versions(project_id):
    if not project_id:
        return []
    return [(f'第 {item["epoch"]} 轮' + (' · 已入库' if item.get('approved') else ' · 已保存'), item['id'])
            for item in training.read_project(project_id)['candidates']]


def create(name):
    try:
        project_id = training.create_project(name)
        return gr.Dropdown(choices=training.choices(), value=project_id), training.summary(project_id)
    except Exception as exc:
        raise gr.Error(str(exc)) from exc


def add(project_id, train, holdout, probes):
    try:
        return training.add_materials(project_id, train, holdout, probes)
    except Exception as exc:
        raise gr.Error(str(exc)) from exc


def select_project(project_id):
    picks = versions(project_id)
    return (training.summary(project_id) if project_id else '请选择训练声线',
            gr.Dropdown(choices=picks, value=picks[-1][1] if picks else None))


def report(project_id, version_id):
    if not project_id or not version_id:
        return [], gr.Dropdown(choices=[], value=None), '尚未生成验收报告'
    item = training.candidate(project_id, version_id)
    if not item.get('report') or not Path(item['report']).exists():
        return [], gr.Dropdown(choices=[], value=None), '当前版本尚未完成验收'
    data = json.loads(Path(item['report']).read_text(encoding='utf-8'))
    rows = [[sample['name'], '跨声线测试' if sample['split'] == 'probes' else '目标声线验证',
             round(sample['speaker_cosine'], 3), round(sample['duration_ratio'], 3),
             round(sample['clipping_ratio'] * 100, 3), '正常' if sample['technical_pass'] else '异常']
            for sample in data['samples']]
    picks = [(sample['name'], str(number)) for number, sample in enumerate(data['samples'])]
    return rows, gr.Dropdown(choices=picks, value='0' if picks else None), data['note']


def sample(project_id, version_id, sample_id):
    if not project_id or not version_id or sample_id is None:
        return None, None
    item = training.candidate(project_id, version_id)
    if not item.get('report'):
        return None, None
    data = json.loads(Path(item['report']).read_text(encoding='utf-8'))
    selected = data['samples'][int(sample_id)]
    return selected['source'], selected['converted']


def train(project_id, epochs, interval, batch, checkpointing):
    STOP.clear()
    try:
        for message in training.train_voice(project_id, epochs, interval, batch, STOP, checkpointing):
            picks = versions(project_id)
            yield message, gr.Dropdown(choices=picks, value=picks[-1][1] if picks else None)
    except Exception as exc:
        raise gr.Error(str(exc)) from exc


def evaluate(project_id, version_id):
    STOP.clear()
    try:
        for message in training.evaluate(project_id, version_id, STOP):
            yield message
    except Exception as exc:
        raise gr.Error(str(exc)) from exc


def stop():
    STOP.set()
    return '正在停止训练或验收任务，已保存的版本保留'


def save_stop(project_id):
    try:
        return training.request_save_stop(project_id)
    except Exception as exc:
        raise gr.Error(str(exc)) from exc


def build_training_ui(cover_voice, cover_choices, cover_mode=None):
    gr.Markdown('## 声线训练', elem_classes='section-heading')
    with gr.Row():
        name = gr.Textbox(label='新声线名称')
        create_button = gr.Button('创建训练声线')
    with gr.Row():
        project = gr.Dropdown(label='训练声线', choices=training.choices(), interactive=True, scale=3)
        refresh = gr.Button('刷新声线')
    status = gr.Textbox(label='训练状态', lines=5, interactive=False)
    gr.Markdown('## 素材', elem_classes='section-heading')
    materials = gr.File(label='训练素材', file_count='multiple', type='filepath', height=150)
    with gr.Accordion('验证素材（可选）', open=False):
        with gr.Row():
            holdout = gr.File(label='目标声线验证素材', file_count='multiple', type='filepath')
            probes = gr.File(label='跨声线测试素材', file_count='multiple', type='filepath')
    add_button = gr.Button('添加素材')
    with gr.Accordion('训练设置', open=True):
        with gr.Row():
            epochs = gr.Number(label='本次追加轮数', value=5, minimum=1, maximum=1000, precision=0, min_width=150)
            interval = gr.Number(label='验收间隔 / 轮', value=5, minimum=1, maximum=100, precision=0, min_width=150)
            batch = gr.Radio([1, 2, 4], label='训练批量', value=4)
        checkpointing = gr.Checkbox(label='省显存训练（较慢）', value=False)
    with gr.Row():
        start = gr.Button('开始／继续训练', variant='primary', elem_classes='primary-action')
        save_stop_button = gr.Button('保存后停止')
        stop_button = gr.Button('立即停止', variant='stop')
    gr.Markdown('## 模型版本', elem_classes='section-heading')
    version = gr.Dropdown(label='候选训练版本', choices=[], interactive=True)
    bypass_confirmed = gr.Checkbox(label='跳过完整验收，直接使用当前模型', value=False)
    with gr.Row():
        bypass_button = gr.Button('保存并加入声线库', variant='primary')
    saved_model = gr.File(label='已备份声线模型', interactive=False)
    with gr.Accordion('验收试听', open=False):
        evaluate_button = gr.Button('生成验收试听')
        results = gr.Dataframe(headers=['素材', '用途', '声纹相似度', '时长比例', '削波占比 %', '技术检测'], interactive=False)
        note = gr.Textbox(label='验收结论', interactive=False)
        clip = gr.Dropdown(label='验收片段', choices=[], interactive=True)
        with gr.Row():
            source = gr.Audio(label='测试原声', interactive=False)
            converted = gr.Audio(label='候选声线', interactive=False)
        confirmed = gr.Checkbox(label='已试听，声线相似度、音高、咬字和自然度满足要求', value=False)
        approve_button = gr.Button('验收通过并入库')

    def accept(project_id, version_id, approved):
        try:
            message = training.approve(project_id, version_id, approved)
            return message, gr.Dropdown(choices=cover_choices(), value='rvc:' + project_id)
        except Exception as exc:
            raise gr.Error(str(exc)) from exc

    def save_directly(project_id, version_id, confirmed):
        try:
            message = training.save_without_validation(project_id, version_id, confirmed)
            model, _ = training.active_model(project_id)
            return message, gr.Dropdown(choices=cover_choices(), value='rvc:' + project_id), model
        except Exception as exc:
            raise gr.Error(str(exc)) from exc

    create_button.click(create, name, [project, status], concurrency_id='gpu')
    refresh.click(lambda: gr.Dropdown(choices=training.choices()), outputs=project)
    project.change(select_project, project, [status, version])
    add_button.click(add, [project, materials, holdout, probes], status, concurrency_id='gpu')
    start.click(train, [project, epochs, interval, batch, checkpointing], [status, version], concurrency_id='gpu', concurrency_limit=1).then(report, [project, version], [results, clip, note])
    save_stop_button.click(save_stop, project, status, queue=False)
    stop_button.click(stop, outputs=status, queue=False)
    version.change(report, [project, version], [results, clip, note])
    version.change(lambda: False, outputs=confirmed)
    version.change(lambda: False, outputs=bypass_confirmed)
    clip.change(sample, [project, version, clip], [source, converted])
    evaluate_button.click(evaluate, [project, version], status, concurrency_id='gpu').then(report, [project, version], [results, clip, note])
    accepted = approve_button.click(accept, [project, version, confirmed], [status, cover_voice], concurrency_id='gpu')
    saved = bypass_button.click(save_directly, [project, version, bypass_confirmed], [status, cover_voice, saved_model], concurrency_id='gpu')
    if cover_mode is not None:
        accepted.then(lambda: '声线库', outputs=cover_mode)
        saved.then(lambda: '声线库', outputs=cover_mode)
