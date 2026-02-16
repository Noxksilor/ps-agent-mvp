import subprocess, time, json
from pathlib import Path

JOB = Path(r'C:\ps_jobs\job_0001')
PHOTOSHOP_EXE = Path(r'C:\Users\User\Documents\Zona Downloads\Photoshop\Photoshop.exe')

TASK_JSX = JOB / 'scripts' / 'task.jsx'
CONFIG = JOB / 'config.json'
OUTPUT_DIR = JOB / 'output'
FINAL_PNG = OUTPUT_DIR / 'final.png'
ORCH_LOG = OUTPUT_DIR / 'orchestrator.log'

def log(msg: str):
    OUTPUT_DIR.mkdir(exist_ok=True)
    ORCH_LOG.write_text((ORCH_LOG.read_text(encoding='utf-8', errors='ignore') if ORCH_LOG.exists() else '') + msg + '\n', encoding='utf-8')

def main():
    # читаем config устойчиво к BOM
    cfg = json.loads(CONFIG.read_text(encoding='utf-8-sig'))
    log('Loaded config OK')

    if not PHOTOSHOP_EXE.exists():
        raise FileNotFoundError(f'Photoshop.exe not found: {PHOTOSHOP_EXE}')

    if not TASK_JSX.exists():
        raise FileNotFoundError(f'task.jsx not found: {TASK_JSX}')

    # очистим старый результат
    if FINAL_PNG.exists():
        FINAL_PNG.unlink()

    cmd = [str(PHOTOSHOP_EXE), '-r', str(TASK_JSX)]
    log('Run: ' + ' '.join(cmd))

    # Запуск и ожидание (Photoshop может жить своим процессом  мы ждём файл)
    subprocess.Popen(cmd, cwd=str(JOB))

    timeout_s = 120
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if FINAL_PNG.exists() and FINAL_PNG.stat().st_size > 0:
            log(f'SUCCESS: final.png created: {FINAL_PNG} ({FINAL_PNG.stat().st_size} bytes)')
            print('OK: final.png создан')
            return
        time.sleep(1)

    log('FAIL: timeout waiting for final.png')
    raise TimeoutError('Timeout: final.png not created')

if __name__ == '__main__':
    main()

