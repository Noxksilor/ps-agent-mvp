"""
orchestrator.py — single entrypoint for the ps-agent-mvp pipeline.

Usage:
    python orchestrator.py configjson/example_job.json

What it does:
    1. Reads the job config (JSON) from the path given on the command line.
    2. Resolves all paths relative to the repo root (directory of this file).
    3. Writes a per-run log to  out/<job_id>/run.log
    4. Kills any existing Photoshop process (so -r flag works reliably).
    5. Launches Photoshop.exe -r scripts/task.jsx  directly (no AHK needed).
    6. Polls for the output PNG in  out/  (path taken from config).
    7. Exits with code 0 on success, 1 on any error.

Requirements:
    - Windows with Adobe Photoshop installed.
    - Python 3.8+  (no third-party packages required).
"""

import os
import sys
import json
import time
import shutil
import logging
import subprocess
from pathlib import Path

# ── repo root = directory that contains this file ──────────────────────────
REPO_ROOT = Path(__file__).resolve().parent

# ── JSX script that Photoshop will run ─────────────────────────────────────
TASK_JSX = REPO_ROOT / "scripts" / "task.jsx"


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────

def _kill_photoshop(logger: logging.Logger) -> None:
    """
    Kill any running Photoshop.exe process so the fresh launch with -r works.
    Uses taskkill (Windows built-in) — silently ignores 'not found' errors.
    """
    try:
        result = subprocess.run(
            ["taskkill", "/F", "/IM", "Photoshop.exe"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            logger.info("Killed existing Photoshop.exe process.")
            time.sleep(2)   # give Windows time to release file handles
        # returncode 128 = process not found — that's fine
    except Exception as exc:
        logger.debug(f"taskkill skipped: {exc}")


def _setup_logger(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove any handlers from a previous call (important when run in a loop)
    logger = logging.getLogger("orchestrator")
    logger.handlers.clear()
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
    logger.info(f"RepoRoot : {REPO_ROOT}")

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

    # 4. Prepare output directory ─────────────────────────────────────────────
    final_png.parent.mkdir(parents=True, exist_ok=True)

    # Remove stale output so we can detect fresh creation
    if final_png.exists():
        final_png.unlink()
        logger.info("Removed stale output PNG.")

    # 5. Write runtime config.json at repo root ──────────────────────────────
    # task.jsx reads config.json from the repo root (two levels above itself).
    # We write a runtime copy so the JSX picks up the correct export path.
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

    # 6. Kill any existing Photoshop so -r flag works reliably ────────────────
    _kill_photoshop(logger)

    # 7. Launch Photoshop directly with -r flag ───────────────────────────────
    #
    # Photoshop.exe -r <jsx_path>
    #   Launches PS and immediately runs the JSX script.
    #   This only works reliably when NO other PS instance is running.
    #
    # We use CREATE_NEW_CONSOLE so the process is fully detached from our
    # terminal, and we do NOT wait for it (Photoshop stays open after the
    # script finishes — we detect completion via the output file).

    cmd = [str(ps_exe), "-r", str(TASK_JSX)]
    logger.info("Launching Photoshop: " + " ".join(f'"{c}"' for c in cmd))

    try:
        # CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS keeps PS independent
        DETACHED_PROCESS = 0x00000008
        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            creationflags=DETACHED_PROCESS,
            close_fds=True,
        )
        logger.info(f"Photoshop launched (PID {proc.pid}). Waiting for output…")
    except OSError as exc:
        logger.error(f"Failed to launch Photoshop: {exc}")
        return 1

    # 8. Poll for output PNG ──────────────────────────────────────────────────
    timeout_s = int(cfg.get("timeout_seconds", 180))
    logger.info(f"Polling for {final_png.name} (timeout {timeout_s}s) …")

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
        time.sleep(2)

    logger.error(
        f"TIMEOUT after {timeout_s}s — {final_png} was not created.\n"
        f"  Check {log_path} for JSX-side errors.\n"
        f"  Also check {REPO_ROOT / 'out' / 'bootstrap.log'} for early JSX errors."
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
