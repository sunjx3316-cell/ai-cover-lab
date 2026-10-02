import os
import subprocess
import time


def terminate_tree(process):
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        import signal
        os.killpg(process.pid, signal.SIGTERM)
    process.wait(timeout=20)


def run_process(command, log, cwd, stop=None):
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
    env = dict(os.environ, PYTHONUTF8='1', PYTHONUNBUFFERED='1', OMP_NUM_THREADS='4')
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('w', encoding='utf-8') as stream:
        process = subprocess.Popen([str(arg) for arg in command], cwd=cwd, stdout=stream,
                                   stderr=subprocess.STDOUT, env=env, **options)
        try:
            while process.poll() is None:
                if stop and stop.is_set():
                    raise RuntimeError('任务已停止')
                time.sleep(1)
                with log.open(encoding='utf-8', errors='replace') as reader:
                    reader.seek(max(0, log.stat().st_size - 3000))
                    detail = reader.read()[-1200:]
                yield detail
        finally:
            if process.poll() is None:
                terminate_tree(process)
    if process.returncode:
        raise RuntimeError(f'后端退出码 {process.returncode}，日志：{log}\n' + log.read_text(encoding='utf-8', errors='replace')[-2500:])
