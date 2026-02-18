"""
orchestrator.py — single entrypoint for the ps-agent-mvp pipeline.

Usage:
    python orchestrator.py configjson/example_job.json

Strategy (works with portable / non-standard Photoshop builds):
    1. Read job config JSON.
    2. Write runtime config.json at repo root (for task.jsx to read).
    3. Kill any existing Photoshop process.
    4. Launch Photoshop.exe  (no -r flag — just open it).
    5. Wait until Photoshop is ready via Windows COM (win32com).
    6. Call  app.doScript(jsx_path, language)  via COM — this is the
       reliable way to run a JSX regardless of how PS was installed.
    7. Poll for the output PNG.
    8. Exit 0 on success, 1 on failure.

Requirements:
    - Windows, Python 3.8+
    - pywin32:  pip install pywin32
    - Adobe Photoshop (any version, including portable builds)
"""

import os
import sys
import json
import time
import logging
import subprocess
from pathlib import Path

# ── repo root = directory that contains this file ──────────────────────────
REPO_ROOT = Path(__file__).resolve().parent

# ── JSX script that Photoshop will run ─────────────────────────────────────
TASK_JSX = REPO_ROOT / "scripts" / "task.jsx"

# ── COM prog-id for Photoshop ───────────────────────────────────────────────
# All modern Photoshop versions register one of these COM prog-ids.
PS_PROGIDS = [
    "Photoshop.Application",       # CS3–CC 2024 (most common)
    "Photoshop.Application.1",
]

# ── ScriptLanguage constant for doScript ───────────────────────────────────
# 2 = javascript (ExtendScript / JSX)
JAVASCRIPT = 2


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────

def _setup_logger(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("orchestrator")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


def _kill_photoshop(logger: logging.Logger) -> None:
    """Kill any running Photoshop.exe so we start fresh."""
    try:
        result = subprocess.run(
            ["taskkill", "/F", "/IM", "Photoshop.exe"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            logger.info("Killed existing Photoshop.exe process.")
            time.sleep(3)   # give Windows time to release COM registration
    except Exception as exc:
        logger.debug(f"taskkill skipped: {exc}")


def _launch_photoshop(ps_exe: Path, logger: logging.Logger) -> None:
    """Launch Photoshop.exe without any script flag (just open it)."""
    DETACHED_PROCESS = 0x00000008
    proc = subprocess.Popen(
        [str(ps_exe)],
        cwd=str(REPO_ROOT),
        creationflags=DETACHED_PROCESS,
        close_fds=True,
    )
    logger.info(f"Launched Photoshop (PID {proc.pid}). Waiting for COM registration…")


def _get_ps_com(timeout_s: int, logger: logging.Logger):
    """
    Wait until Photoshop registers its COM object, then return the app object.
    Tries each prog-id in PS_PROGIDS.
    Raises RuntimeError if timeout is reached.
    """
    try:
        import win32com.client
    except ImportError:
        raise RuntimeError(
            "pywin32 is not installed. Run:  pip install pywin32\n"
            "Then re-run the orchestrator."
        )

    t0 = time.monotonic()
    attempt = 0
    while time.monotonic() - t0 < timeout_s:
        attempt += 1
        for progid in PS_PROGIDS:
            try:
                app = win32com.client.Dispatch(progid)
                # Accessing .version proves PS is actually ready
                ver = app.Version
                logger.info(f"Photoshop COM ready (progid={progid}, version={ver}).")
                return app
            except Exception:
                pass
        if attempt % 5 == 0:
            elapsed = int(time.monotonic() - t0)
            logger.info(f"  Still waiting for Photoshop COM… ({elapsed}s elapsed)")
        time.sleep(2)

    raise RuntimeError(
        f"Photoshop COM object not available after {timeout_s}s. "
        "Make sure Photoshop is installed and COM is registered."
    )


def _run_jsx_via_com(app, jsx_path: Path, repo_root: Path,
                     logger: logging.Logger) -> None:
    """
    Execute a JSX file inside the running Photoshop via COM DoJavaScript().

    When code is passed as a string (not a file), $.fileName is empty inside
    the script. We inject __jsxFile__ AND __jobRoot__ directly from Python so
    task.jsx never needs to do any path resolution — it just uses __jobRoot__.
    """
    # Suppress all dialogs so the script runs unattended
    try:
        app.DisplayDialogs = 3   # psDisplayNoDialogs = 3
    except Exception:
        pass

    logger.info(f"Reading JSX source: {jsx_path}")
    jsx_source = jsx_path.read_text(encoding="utf-8")

    # Inject absolute paths with forward slashes (safe in ExtendScript strings)
    jsx_path_fwd  = str(jsx_path).replace("\\", "/")
    repo_root_fwd = str(repo_root).replace("\\", "/")

    preamble = (
        f'var __jsxFile__  = "{jsx_path_fwd}";\n'
        f'var __jobRoot__  = "{repo_root_fwd}";\n'
    )
    full_source = preamble + jsx_source

    logger.info(f"Injected __jobRoot__ = {repo_root_fwd}")
    logger.info(f"Calling app.DoJavaScript() ({len(full_source)} chars) …")

    # DoJavaScript(javascript, arguments, executionMode)
    #   javascript    : ExtendScript source code string
    #   arguments     : array of arguments (pass empty list)
    #   executionMode : 1 = normal (synchronous)
    result = app.DoJavaScript(full_source, [], 1)

    logger.info(f"DoJavaScript() returned: {result!r}")
    logger.info("JSX execution complete (Photoshop processed the script).")


# ───────────────────────────────────────────────────────────────────────────
# Main pipeline
# ───────────────────────────────────────────────────────────────────────────

def run_pipeline(config_path: Path) -> int:
    """Execute the full pipeline. Returns 0 on success, 1 on failure."""

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

    # 2. Resolve output paths ─────────────────────────────────────────────────
    #
    # export_png_path: the path JSX writes to (may be absolute, e.g. C:/Users/Public/...)
    # local_png:       always inside out/<job_id>/  — the canonical output for the user
    #
    # If export_png_path is absolute → JSX writes there; orchestrator copies to local_png.
    # If export_png_path is relative → JSX writes to REPO_ROOT/path; that IS local_png.

    export_png_path_str = (
        cfg.get("export", {}).get("png", {}).get("path") or f"out/{job_id}/final.png"
    )
    export_png_path = Path(export_png_path_str)
    if not export_png_path.is_absolute():
        export_png_path = REPO_ROOT / export_png_path_str

    # The canonical local output (always in out/<job_id>/)
    local_png: Path = REPO_ROOT / "out" / job_id / "final.png"

    # If JSX writes directly to local_png, no copy needed
    needs_copy = export_png_path.resolve() != local_png.resolve()

    log_path = local_png.parent / "run.log"
    logger = _setup_logger(log_path)

    logger.info("=" * 60)
    logger.info(f"Job        : {job_id}")
    logger.info(f"Config     : {config_path}")
    logger.info(f"JSX output : {export_png_path}  (where JSX saves the PNG)")
    logger.info(f"Local PNG  : {local_png}  (final destination)")
    logger.info(f"Copy needed: {needs_copy}")
    logger.info(f"JSX        : {TASK_JSX}")
    logger.info(f"RepoRoot   : {REPO_ROOT}")

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

    # 4. Prepare output directories ───────────────────────────────────────────
    local_png.parent.mkdir(parents=True, exist_ok=True)

    # Remove stale files so we can detect fresh creation
    if export_png_path.exists():
        export_png_path.unlink()
        logger.info(f"Removed stale JSX output: {export_png_path}")
    if local_png.exists():
        local_png.unlink()
        logger.info(f"Removed stale local PNG: {local_png}")

    # 5. Write runtime config.json ────────────────────────────────────────────
    # Pass the export path exactly as configured so JSX writes to the right place.
    runtime_cfg = dict(cfg)
    runtime_cfg["export"] = {
        "png": {"path": export_png_path_str},   # keep original (may be absolute)
        "psd": cfg.get("export", {}).get("psd", {"enabled": False}),
    }
    runtime_config_path = REPO_ROOT / "config.json"
    runtime_config_path.write_text(
        json.dumps(runtime_cfg, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    logger.info(f"Wrote runtime config.json → {runtime_config_path}")

    # 6. Kill stale PS, launch fresh ──────────────────────────────────────────
    _kill_photoshop(logger)
    _launch_photoshop(ps_exe, logger)

    # 7. Wait for Photoshop COM to become available ───────────────────────────
    ps_startup_timeout = int(cfg.get("ps_startup_timeout_seconds", 60))
    try:
        ps_app = _get_ps_com(ps_startup_timeout, logger)
    except RuntimeError as exc:
        logger.error(str(exc))
        return 1

    # 8. Run JSX via COM DoJavaScript ─────────────────────────────────────────
    try:
        _run_jsx_via_com(ps_app, TASK_JSX, REPO_ROOT, logger)
    except Exception as exc:
        logger.error(f"DoJavaScript failed: {exc}")
        return 1

    # 9. Poll for JSX output PNG ──────────────────────────────────────────────
    timeout_s = int(cfg.get("timeout_seconds", 180))
    logger.info(
        f"Polling for JSX output: {export_png_path}  (timeout {timeout_s}s) …"
    )

    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        if export_png_path.exists() and export_png_path.stat().st_size > 0:
            elapsed = time.monotonic() - t0
            size_kb = export_png_path.stat().st_size / 1024
            logger.info(
                f"JSX output ready: {export_png_path.name} "
                f"({size_kb:.1f} KB, {elapsed:.1f}s elapsed)"
            )

            # 10. Copy to local output path ───────────────────────────────────
            if needs_copy:
                import shutil
                shutil.copy2(str(export_png_path), str(local_png))
                logger.info(
                    f"Copied to local PNG: {local_png} "
                    f"({local_png.stat().st_size / 1024:.1f} KB)"
                )
            else:
                logger.info(f"Local PNG is the same file — no copy needed.")

            logger.info(f"SUCCESS — final PNG: {local_png}")
            return 0
        time.sleep(2)

    # TIMEOUT — point user to the JSX debug logs in C:\Users\Public\...
    # (this Photoshop build can only write there)
    logger.error(
        f"TIMEOUT after {timeout_s}s — JSX output not found at: {export_png_path}\n"
        f"\n"
        f"  JSX debug logs (check these for errors):\n"
        f"    C:\\Users\\Public\\ps_agent_jsx_debug.txt\n"
        f"    C:\\Users\\Public\\ps_agent_bootstrap.log\n"
        f"\n"
        f"  Orchestrator log: {log_path}"
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
    if not config_path.is_absolute():
        config_path = REPO_ROOT / config_path

    exit_code = run_pipeline(config_path)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
