import lab_env
import faulthandler
faulthandler.enable()
faulthandler.dump_traceback_later(60, repeat=True)
print('Starting local cover interface...', flush=True)
import json
import os
import threading
import time
import uuid
from pathlib import Path

import gradio as gr
print('Gradio imported.', flush=True)
from audio_workflow import create_job, decode, stage, validate, mix
from exports import save_export, restore_latest, create_server
import voice_training
from process_runner import run_process
from voice_selection import resolve_source
print('Audio workflow imported.', flush=True)

os.environ['PATH'] = str(lab_env.ROOT / 'runtime') + os.pathsep + os.environ.get('PATH', '')
VOICES = lab_env.ROOT / 'voices'
VOICES.mkdir(exist_ok=True)
STOP = threading.Event()

def voice_choices():
    references = [(json.loads(item.read_text(encoding='utf-8'))['name'] + ' · 参考', item.parent.name) for item in sorted(VOICES.glob('*/profile.json'))]
    trained = [(name + ' · ' + str(voice_training.read_project(key)['active']['epoch']) + '轮',
                'rvc:' + key) for name, key in voice_training.choices(approved_only=True)]
    return trained + references

def upload_preview(file, duration, mono=False):
    if not file:
        return gr.Audio(value=None, visible=False)
    folder = lab_env.ROOT / 'temp' / 'previews' / uuid.uuid4().hex
    folder.mkdir(parents=True)
    target = folder / 'preview.wav'
    try:
        decode(file, target, duration=duration, mono=mono)
    except Exception as exc:
        raise gr.Error(str(exc)) from exc
    return gr.Audio(value=str(target), visible=True)

def reference_preview(file):
    return upload_preview(file, 10, mono=True)

def song_preview(file):
    return upload_preview(file, 30)

def save_voice(file, name):
    if not file:
        raise gr.Error('请先上传目标声线')
    voice_id = uuid.uuid4().hex[:12]
    folder = VOICES / voice_id
    folder.mkdir()
    try:
        decode(file, folder / 'reference.wav', duration=10, mono=True)
        if validate(folder / 'reference.wav')['rms'] < 1e-5:
            raise gr.Error('这份参考音频接近静音，请换一段清晰的人声')
        title = name.strip() or Path(file).stem
        (folder / 'profile.json').write_text(json.dumps({'name': title, 'id': voice_id}, ensure_ascii=False), encoding='utf-8')
    except Exception as exc:
        # Only remove files from the just-created, uniquely named voice folder.
        import shutil
        shutil.rmtree(folder)
        raise gr.Error(str(exc)) from exc
    return gr.Dropdown(choices=voice_choices(), value=voice_id), f'已保存声线：{title}'

def stop_job():
    STOP.set()
    return '正在停止当前任务…'

def delete_voice(voice_id):
    if not voice_id:
        raise gr.Error('请先选择声线')
    if voice_id.startswith('rvc:'):
        data = voice_training.read_project(voice_id[4:])
        data['active'] = None
        voice_training.write_json(voice_training.project_path(voice_id[4:]) / 'profile.json', data)
        return gr.Dropdown(choices=voice_choices(), value=None), '已移出翻唱声线库，训练素材和版本保留'
    folder = (VOICES / voice_id).resolve()
    if folder.parent != VOICES.resolve() or not (folder / 'profile.json').is_file():
        raise gr.Error('声线不存在')
    import shutil
    shutil.rmtree(folder)
    return gr.Dropdown(choices=voice_choices(), value=None), '声线已删除'

def pipeline(reference, voice_id, song, pure_vocal, steps, pitch, start, duration, vocal_gain, harmony_gain, source_mode=None):
    if not song:
        raise gr.Error('请上传歌曲或纯人声音轨')
    try:
        trained, reference, voice_id = resolve_source(reference, voice_id, source_mode)
        if trained:
            model, index = voice_training.active_model(voice_id[4:])
    except Exception as exc:
        raise gr.Error(str(exc)) from exc
    STOP.clear()
    job = create_job()
    lead = backing = converted = cover = instrumental = None
    ref = job / 'reference.wav'
    source_ref = reference or VOICES / (voice_id or '') / 'reference.wav'
    started = time.monotonic()
    try:
        if not trained:
            if not (lab_env.ROOT / 'models/YingMusic-SVC-full.pt').exists():
                raise ValueError('免训练转换后端未安装。请选择已训练声线，或运行 powershell -ExecutionPolicy Bypass -File setup.ps1 -Feature Ying 安装可选后端。')
            decode(source_ref, ref, duration=10, mono=True)
        decode(song, job / 'input/song.wav', start=start, duration=duration)
        (job / 'settings.json').write_text(json.dumps({'engine': 'Applio/RVC' if trained else 'YingMusic-SVC', 'voice_id': voice_id, 'steps': steps, 'pitch': pitch, 'start': start, 'duration': duration, 'vocal_gain_db': vocal_gain, 'original_harmony_gain_db': harmony_gain}), encoding='utf-8')
        if pure_vocal:
            lead = job / 'input/song.wav'
        else:
            yield '正在分离主唱、和声与伴奏…', None, None, None, None, None
            for log in stage('separate', job, job / 'input', stop=STOP):
                yield f'正在分离 · 已运行 {int(time.monotonic() - started)} 秒', None, None, None, None, None
            stems = job / 'song'
            lead, backing, instrumental = [stems / f'{name}.wav' for name in ('vocals', 'backing_vocal', 'instrumental')]
            for path in (lead, backing, instrumental):
                validate(path)
        if trained:
            converted = job / 'converted' / 'rvc.wav'
            conversion = run_process(voice_training.rvc_command(lead, converted, model, index, int(pitch)),
                                     job / 'convert.log', voice_training.APPLIO, STOP)
        else:
            conversion = stage('convert', job, lead, reference=ref, steps=int(steps), pitch=int(pitch), stop=STOP)
        for log in conversion:
            yield f'正在转换声线 · 已运行 {int(time.monotonic() - started)} 秒', str(lead), str(backing) if backing else None, None, None, None
        converted = next((job / 'converted').glob('*.wav'))
        stats = validate(converted)
        if stats['rms'] < 1e-5:
            raise RuntimeError('转换结果接近静音，请检查参考音频和分离主唱')
        cover = job / 'cover.wav'
        mix_stats = mix(converted, instrumental, backing, cover, vocal_gain, harmony_gain)
        (job / 'validation.json').write_text(json.dumps({'vocal': stats, 'mix': mix_stats}), encoding='utf-8')
        yield f'制作完成 · {int(time.monotonic() - started)} 秒', str(lead), str(backing) if backing else None, str(converted), str(cover), str(cover)
    except Exception as exc:
        (job / 'error.txt').write_text(str(exc), encoding='utf-8')
        if STOP.is_set():
            yield '任务已停止', str(lead) if lead else None, str(backing) if backing else None, None, None, None
        else:
            raise gr.Error(f'制作失败，日志位于 {job}\n{str(exc)[-1600:]}')

def preferred_voice():
    choices = voice_choices()
    return choices[0][1] if choices else None


def voice_description(value):
    if not value:
        return '尚未选择声线', gr.Slider(interactive=True)
    if value.startswith('rvc:'):
        data = voice_training.read_project(value[4:])
        active = data.get('active')
        if not active:
            return '模型未入库', gr.Slider(interactive=False)
        checked = '未完整验收' if active.get('validation_bypassed') else '已验收'
        return f'RVC · 第 {active["epoch"]} 轮 · 已保存 · {checked}', gr.Slider(interactive=False)
    return 'YingMusic · 参考声线', gr.Slider(interactive=True)


def switch_source(mode, voice_id):
    library = mode == '声线库'
    details, slider = voice_description(voice_id) if library else ('YingMusic · 参考音频', gr.Slider(interactive=True))
    return gr.Column(visible=not library), gr.Dropdown(interactive=library), details, slider


def refresh_voices(value):
    options = voice_choices()
    selected = value if any(key == value for _, key in options) else preferred_voice()
    return gr.Dropdown(choices=options, value=selected, interactive=True)


css = '''
.gradio-container { max-width: 1160px !important; margin: 0 auto !important; padding: 24px 28px 40px !important; }
.gradio-container, .gradio-container input, .gradio-container textarea, .gradio-container button { font-family: "Segoe UI", "Microsoft YaHei", sans-serif !important; letter-spacing: 0 !important; }
.lab-header { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 4px 0 22px; border-bottom: 1px solid #dfe4e2; }
.lab-header h1 { margin: 0; font-size: 26px; line-height: 1.25; color: #202826; font-weight: 650; }
.lab-header .local { font-size: 12px; color: #59645f; border-left: 3px solid #2b947a; padding-left: 10px; white-space: nowrap; }
.gradio-container .tabs { border: 0 !important; background: transparent !important; }
.gradio-container .tab-nav { gap: 26px; border-bottom: 1px solid #dfe4e2 !important; padding: 0 !important; margin-bottom: 24px; }
.gradio-container .tab-nav button { border: 0 !important; border-radius: 0 !important; background: transparent !important; padding: 14px 2px !important; font-size: 15px !important; color: #68736d !important; }
.gradio-container .tab-nav button.selected { color: #17745e !important; box-shadow: inset 0 -2px #21856a !important; font-weight: 650; }
.gradio-container .tabitem { padding: 0 !important; border: 0 !important; }
.gradio-container .block { border-radius: 8px !important; box-shadow: none !important; }
.gradio-container button { border-radius: 6px !important; min-height: 40px; white-space: normal !important; }
.section-heading { margin: 0 0 10px !important; padding: 0 !important; border: 0 !important; }
.section-heading h2 { margin: 0 !important; font-size: 17px !important; font-weight: 650; color: #27332d; }
.voice-state textarea { color: #17745e !important; font-size: 13px !important; }
#cover-voice { min-width: 0 !important; }
#cover-voice input { min-width: 0 !important; text-overflow: ellipsis; }
#cover-voice .wrap, #cover-voice .secondary-wrap { min-width: 0 !important; }
.primary-action { min-height: 46px !important; font-weight: 650 !important; }
.result-section { margin-top: 16px; padding-top: 22px; border-top: 1px solid #dfe4e2; }
.export-link a { color: #17745e; font-weight: 600; text-decoration: underline; }
.dark .lab-header h1, .dark .section-heading h2 { color: #e3ece6; }
.dark .lab-header .local { color: #a6b6ac; }
.dark .lab-header, .dark .result-section, .dark .tab-nav { border-color: #39463e !important; }
.dark .voice-state textarea, .dark .export-link a { color: #82ccb1 !important; }
.dark .tab-nav button.selected { color: #82ccb1 !important; }
footer { display: none !important; }
@media (max-width: 640px) {
  .gradio-container { padding: 16px 14px 28px !important; }
  .lab-header { gap: 10px; padding-bottom: 18px; }
  .lab-header h1 { font-size: 23px; }
  .lab-header .local { font-size: 11px; }
  .gradio-container .tab-nav { gap: 22px; }
}
'''
theme = gr.themes.Default(primary_hue='emerald', secondary_hue='rose', neutral_hue='gray').set(
    body_background_fill='#f7f9f8', body_background_fill_dark='#171c1a',
    block_background_fill='#ffffff', block_border_color='#dfe4e2',
    block_radius='8px', button_primary_background_fill='#207e64',
    button_primary_background_fill_hover='#18664f', button_primary_text_color='#ffffff',
    button_secondary_background_fill='#ffffff', button_secondary_border_color='#d5ddd8',
    input_background_fill='#ffffff', input_border_color='#d5ddd8',
)
with gr.Blocks(title='AI Cover Lab', css=css, theme=theme) as app:
    gr.HTML('<header class="lab-header"><h1>AI Cover Lab</h1><span class="local">本地会话</span></header>')
    with gr.Tabs():
        with gr.Tab('制作翻唱', id='cover'):
            with gr.Row(equal_height=False):
                with gr.Column(scale=1, min_width=280):
                    gr.Markdown('## 声线', elem_classes='section-heading')
                    source_mode = gr.Radio(['声线库', '参考音频'], value='声线库', label='声线来源')
                    voice = gr.Dropdown(label='翻唱声线', choices=voice_choices(), value=preferred_voice(),
                                        interactive=True, filterable=True, elem_id='cover-voice')
                    with gr.Row():
                        refresh_voice = gr.Button('刷新声线库', size='sm')
                        delete = gr.Button('移除声线', size='sm')
                    voice_info = gr.Textbox(label='当前模型', value=voice_description(preferred_voice())[0],
                                            interactive=False, lines=1, elem_classes='voice-state')
                    with gr.Column(visible=False) as reference_group:
                        reference = gr.File(label='目标参考音频', type='filepath', file_count='single', file_types=None)
                        reference_player = gr.Audio(label='参考试听', interactive=False, visible=False)
                        name = gr.Textbox(label='参考声线名称')
                        save = gr.Button('保存参考声线')
                with gr.Column(scale=2, min_width=300):
                    gr.Markdown('## 歌曲', elem_classes='section-heading')
                    song = gr.File(label='需要翻唱的歌曲', type='filepath', file_count='single', file_types=None, height=150)
                    song_player = gr.Audio(label='歌曲试听', interactive=False, visible=False)
                    pure = gr.Checkbox(label='纯人声音轨', value=False)
                    with gr.Row():
                        start = gr.Number(label='起始位置 / 秒', value=0, minimum=0, min_width=130)
                        duration = gr.Number(label='制作时长 / 秒（0 为整首）', value=30, minimum=0, min_width=170)
                    with gr.Accordion('音高与混音', open=False):
                        pitch = gr.Slider(label='移调 / 半音', minimum=-12, maximum=12, step=1, value=0)
                        vocal_gain = gr.Slider(label='翻唱人声 / dB', minimum=-12, maximum=12, step=1, value=3)
                        harmony_gain = gr.Slider(label='原曲和声 / dB（-48 关闭）', minimum=-48, maximum=0, step=1, value=-16)
                        steps = gr.Slider(label='YingMusic 推理步数', minimum=10, maximum=100, step=10, value=50,
                                          interactive=not bool(preferred_voice() and preferred_voice().startswith('rvc:')))
                    with gr.Row():
                        run = gr.Button('开始制作', variant='primary', scale=3, elem_classes='primary-action')
                        stop = gr.Button('停止', scale=1)
            status = gr.Textbox(label='制作状态', value='就绪', interactive=False, lines=2)
            with gr.Column(elem_classes='result-section'):
                gr.Markdown('## 成品', elem_classes='section-heading')
                output = gr.Audio(label='成品歌曲', type='filepath', interactive=False)
                with gr.Row():
                    export_format = gr.Radio(['WAV', 'MP3'], value='MP3', label='导出格式', scale=1)
                    export_button = gr.Button('保存音频到本机', scale=2)
                export_status = gr.Textbox(label='保存位置', interactive=False)
                attachment_link = gr.HTML(elem_classes='export-link')
                with gr.Accordion('成品文件', open=False):
                    download = gr.File(label='下载成品', interactive=False)
                with gr.Accordion('分轨试听', open=False):
                    lead_out = gr.Audio(label='分离主唱', interactive=False)
                    backing_out = gr.Audio(label='分离和声', interactive=False)
                    converted_out = gr.Audio(label='转换后人声', interactive=False)
        with gr.Tab('训练声线', id='training'):
            from training_ui import build_training_ui
            build_training_ui(voice, voice_choices, source_mode)
    save.click(save_voice, [reference, name], [voice, status]).then(lambda: '声线库', outputs=source_mode)
    export_button.click(save_export, [download, export_format], [download, export_status, attachment_link], concurrency_limit=1)
    app.load(restore_latest, outputs=[output, download])
    reference.change(reference_preview, reference, reference_player, queue=False)
    song.change(song_preview, song, song_player, queue=False)
    app.load(refresh_voices, voice, voice, queue=False)
    refresh_voice.click(refresh_voices, voice, voice, queue=False)
    delete.click(delete_voice, voice, [voice, status])
    voice.change(voice_description, voice, [voice_info, steps], queue=False)
    voice.input(lambda: '声线库', outputs=source_mode, queue=False)
    source_mode.change(switch_source, [source_mode, voice], [reference_group, voice, voice_info, steps], queue=False)
    stop.click(stop_job, outputs=status, queue=False)
    run.click(pipeline, [reference, voice, song, pure, steps, pitch, start, duration, vocal_gain, harmony_gain, source_mode],
              [status, lead_out, backing_out, converted_out, output, download], concurrency_id='gpu', concurrency_limit=1)

if __name__ == '__main__':
    port = int(os.environ.get('AI_COVER_PORT', '7867'))
    if not 1024 <= port <= 65535:
        raise ValueError('AI_COVER_PORT must be between 1024 and 65535')
    print(f'Launching on http://127.0.0.1:{port}', flush=True)
    faulthandler.cancel_dump_traceback_later()
    import uvicorn
    server = gr.mount_gradio_app(create_server(), app.queue(default_concurrency_limit=1), path='/',
                                 allowed_paths=[str(lab_env.ROOT / 'outputs'), str(lab_env.ROOT / 'exports'), str(lab_env.ROOT / 'training')])
    uvicorn.run(server, host='127.0.0.1', port=port)
