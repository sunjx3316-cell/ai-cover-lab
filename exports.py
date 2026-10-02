import lab_env
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from audio_workflow import FFMPEG, validate

EXPORTS = lab_env.ROOT / 'exports'


def export_audio(file, format='WAV'):
    if not file:
        raise ValueError('还没有可下载的成品，请先完成制作')
    source = Path(file).resolve()
    allowed = [lab_env.ROOT / 'outputs', lab_env.ROOT / 'temp' / 'gradio', EXPORTS]
    if not any(source.is_relative_to(folder.resolve()) for folder in allowed) or not source.is_file():
        raise ValueError('成品文件不存在或路径无效')
    extension = {'WAV': 'wav', 'MP3': 'mp3'}.get(format)
    if not extension:
        raise ValueError('不支持的导出格式')
    validate(source)
    digest = hashlib.sha256()
    with source.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    EXPORTS.mkdir(exist_ok=True)
    target = EXPORTS / f'AI-cover-{digest.hexdigest()[:16]}.{extension}'
    if not target.exists():
        temporary = target.with_name(target.stem + '.part.' + extension)
        if extension == 'wav':
            shutil.copy2(source, temporary)
        else:
            options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
            subprocess.run([str(FFMPEG), '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source),
                            '-vn', '-c:a', 'libmp3lame', '-b:a', '320k', str(temporary)], check=True, capture_output=True, **options)
        validate(temporary)
        os.replace(temporary, target)
    return target


def save_export(file, format):
    import gradio as gr
    try:
        target = export_audio(file, format)
    except Exception as exc:
        raise gr.Error(str(exc)) from exc
    link = f'<a href="/download/{html.escape(target.name)}" download="{html.escape(target.name)}">下载 {html.escape(format)}</a>'
    return str(target), f'已保存到本机：{target}', link


def create_server():
    server = FastAPI()

    @server.get('/lab-health')
    def health():
        token = hashlib.sha256(str(lab_env.ROOT.resolve()).lower().encode('utf-8')).hexdigest()
        return {'application': 'AI Cover Lab', 'version': '0.1.0-beta', 'root_token': token}

    @server.api_route('/download/{filename}', methods=['GET', 'HEAD'])
    def attachment(filename: str):
        if not re.fullmatch(r'AI-cover-[0-9a-f]{16}\.(wav|mp3)', filename):
            raise HTTPException(status_code=404)
        path = EXPORTS / filename
        if not path.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(path, filename=filename, content_disposition_type='attachment',
                            media_type='audio/wav' if filename.endswith('.wav') else 'audio/mpeg')
    return server


def restore_latest():
    candidates = sorted((lab_env.ROOT / 'outputs').glob('*/cover.wav'), key=lambda file: file.stat().st_mtime, reverse=True)
    visible = []
    for file in candidates:
        settings = file.parent / 'settings.json'
        try:
            validation_only = settings.exists() and json.loads(settings.read_text(encoding='utf-8')).get('validation_only')
        except (ValueError, OSError):
            validation_only = False
        if not validation_only:
            visible.append(file)
    candidates = visible
    if not candidates:
        import gradio as gr
        return gr.skip(), gr.skip()
    return str(candidates[0]), str(candidates[0])
