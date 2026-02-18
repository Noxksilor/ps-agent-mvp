"""
orchestrator.py — single entrypoint for the ps-agent-mvp pipeline.

Usage:
    python orchestrator.py configjson/example_job.json

What it does:
    1. Reads the job config (JSON) from the path given on the command line.
    2. Resolves all paths relative to the repo root (directory of this file).
    3. Writes a per-run log to  out/<job_id>/run.log
    4. Launches Photoshop via AutoHotkey (scripts/launch_ps.ahk) so that
       scripts/task.jsx is executed inside Photoshop.
    5. Polls for the output PNG in  out/  (path taken from config).
    6. Exits with code 0 on success, 1 on any error.

Requirements:
    - Windows with AutoHotkey v1 installed and on PATH  (autohotkey.exe)
      OR AutoHotkey v2  (AutoHotkey64.exe / AutoHotkey32.exe).
    - Adobe Photoshop installed; path set in the job config.
    - Python 3.8+
"""

import sys
import json
import time
import shutil
import logging
import subprocess
from datetime import datetime
from pathlib import Path

# ── repo root = directory that contains this file ──────────────────────────
REPO_ROOT = Path(__file__).resolve().parent

# ── AHK script that launches Photoshop ─────────────────────────────────────
AHK_SCRIPT = REPO_ROOT / "scripts" / "launch_ps.ahk"

# ── JSX script that Photoshop will run ─────────────────────────────────────
TASK_JSX = REPO_ROOT / "scripts" / "task.jsx"


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────

def _find_ahk() -> str:
    """Return the AutoHotkey executable name found on PATH, or raise."""
    for candidate in ("AutoHotkey.exe", "AutoHotkey64.exe",
                      "AutoHotkey32.exe", "autohotkey.exe"):
        if shutil.which(candidate):
            return candidate
    raise FileNotFoundError(
        "AutoHotkey not found on PATH. "
        "Install AutoHotkey v1 or v2 and make sure it is on PATH."
    )


def _setup_logger(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("orchestrator")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    # file handler — append so reruns accumulate
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    # console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


# ───────────────────────────────────────────────────────────────────────────
# Main pipeline
# ───────────────────────────────────────────────────────────────────────────

def run_pipeline(config_path: Path) -> int:
    """
    Execute the full pipeline for one job config.
    Returns 0 on success, 1 on failure.
    """

    # 1. Load config ─────────────────────────────────────────────────────────
    if not config_path.exists():
        print(f"ERROR: config not found: {config_path}", file=sys.stderr)
        return 1

    try:
        cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON in {config_path}: {exc}", file=sys.stderr)
        return 1

    job_id = cfg.get("job_id", config_path.stem)

    # 2. Resolve output path from config ─────────────────────────────────────
    export_png_rel = (
        cfg.get("export", {}).get("png", {}).get("path") or f"out/{job_id}/final.png"
    )
    # Paths in config are relative to REPO_ROOT
    final_png: Path = REPO_ROOT / export_png_rel

    # Log goes next to the output PNG
    log_path = final_png.parent / "run.log"
    logger = _setup_logger(log_path)

    logger.info("=" * 60)
    logger.info(f"Job      : {job_id}")
    logger.info(f"Config   : {config_path}")
    logger.info(f"Output   : {final_png}")
    logger.info(f"JSX      : {TASK_JSX}")

    # 3. Validate prerequisites ───────────────────────────────────────────────
    ps_exe_str = cfg.get("photoshop_exe", "")
    ps_exe = Path(ps_exe_str) if ps_exe_str else None

    if not ps_exe or not ps_exe.exists():
        logger.error(
            f"Photoshop.exe not found: '{ps_exe_str}'. "
            "Set 'photoshop_exe' in your job config."
        )
        return 1

    if not TASK_JSX.exists():
        logger.error(f"task.jsx not found: {TASK_JSX}")
        return 1

    if not AHK_SCRIPT.exists():
        logger.error(f"AHK script not found: {AHK_SCRIPT}")
        return 1

    try:
        ahk_exe = _find_ahk()
    except FileNotFoundError as exc:
        logger.error(str(exc))
        return 1

    # 4. Prepare output directory ─────────────────────────────────────────────
    final_png.parent.mkdir(parents=True, exist_ok=True)

    # Remove stale output so we can detect fresh creation
    if final_png.exists():
        final_png.unlink()
        logger.info("Removed stale output PNG.")

    # 5. Copy config to a location the JSX can find ──────────────────────────
    # task.jsx looks for config.json two levels above itself (repo root).
    # We write a temporary config.json at repo root so the JSX picks it up.
    # The JSX resolves paths relative to repo root, so we patch export path too.
    runtime_cfg = dict(cfg)
    runtime_cfg["export"] = {
        "png": {"path": export_png_rel},
        "psd": cfg.get("export", {}).get("psd", {"enabled": False}),
    }
    runtime_config_path = REPO_ROOT / "config.json"
    runtime_config_path.write_text(
        json.dumps(runtime_cfg, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    logger.info(f"Wrote runtime config.json → {runtime_config_path}")

    # 6. Launch Photoshop via AHK ─────────────────────────────────────────────
    cmd = [ahk_exe, str(AHK_SCRIPT), str(ps_exe), str(TASK_JSX)]
    logger.info("Launching: " + " ".join(f'"{c}"' for c in cmd))

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        logger.error(f"Failed to start AHK: {exc}")
        return 1

    # Wait for AHK to finish (it exits after handing off to Photoshop)
    try:
        ahk_stdout, ahk_stderr = proc.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        logger.warning("AHK process timed out — continuing to poll for PNG.")

    if proc.returncode not in (None, 0):
        logger.warning(f"AHK exited with code {proc.returncode}")

    # 7. Poll for output PNG ──────────────────────────────────────────────────
    timeout_s = int(cfg.get("timeout_seconds", 120))
    logger.info(f"Waiting up to {timeout_s}s for {final_png.name} …")

    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        if final_png.exists() and final_png.stat().st_size > 0:
            elapsed = time.monotonic() - t0
            size_kb = final_png.stat().st_size / 1024
            logger.info(
                f"SUCCESS — {final_png.name} created "
                f"({size_kb:.1f} KB, {elapsed:.1f}s elapsed)"
            )
            return 0
        time.sleep(1)

    logger.error(
        f"TIMEOUT after {timeout_s}s — {final_png} was not created. "
        "Check out/<job_id>/run.log (JSX log) for Photoshop-side errors."
    )
    return 1


# ───────────────────────────────────────────────────────────────────────────
# CLI entrypoint
# ───────────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: python orchestrator.py configjson/example_job.json",
            file=sys.stderr,
        )
        sys.exit(1)

    config_path = Path(sys.argv[1])
    # Allow both absolute paths and paths relative to repo root
    if not config_path.is_absolute():
        config_path = REPO_ROOT / config_path

    exit_code = run_pipeline(config_path)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
