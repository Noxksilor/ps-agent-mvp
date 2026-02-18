"""
ps_diag.py — Photoshop pipeline diagnostic tool
================================================

Usage:
    python ps_diag.py
    python ps_diag.py "C:\\path\\to\\Photoshop.exe"

What it does:
    1. Finds Photoshop.exe (from configjson/example_job.json or CLI arg).
    2. Kills any existing Photoshop process.
    3. Launches Photoshop.exe (no -r flag).
    4. Connects via Windows COM (pywin32).
    5. Runs a minimal JSX that tries to write files to FOUR different paths:
         a) C:\\ps_diag_root.txt          — root of C: drive
         b) C:\\Users\\Public\\ps_diag_public.txt  — public user folder
         c) <repo_root>\\out\\jsx_diag.txt — project output folder
         d) <temp>\\ps_diag_temp.txt      — Windows TEMP folder
    6. Checks which files were actually created.
    7. Prints a clear diagnostic report.

Requirements:
    pip install pywin32
"""

import os
import sys
import json
import time
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# ── PS prog-ids ─────────────────────────────────────────────────────────────
PS_PROGIDS = ["Photoshop.Application", "Photoshop.Application.1"]

# ── Diagnostic file paths (hardcoded, no path resolution in JSX) ────────────
DIAG_FILES = {
    "C_root":      r"C:\ps_diag_root.txt",
    "C_public":    r"C:\Users\Public\ps_diag_public.txt",
    "project_out": str(REPO_ROOT / "out" / "jsx_diag.txt"),
    "temp_dir":    str(Path(tempfile.gettempdir()) / "ps_diag_temp.txt"),
}


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────

def _find_ps_exe() -> str:
    """Read photoshop_exe from configjson/example_job.json."""
    cfg_path = REPO_ROOT / "configjson" / "example_job.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
            exe = cfg.get("photoshop_exe", "")
            if exe and Path(exe).exists():
                return exe
        except Exception:
            pass
    return ""


def _kill_photoshop() -> None:
    try:
        r = subprocess.run(["taskkill", "/F", "/IM", "Photoshop.exe"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            print("  [+] Killed existing Photoshop.exe")
            time.sleep(3)
    except Exception:
        pass


def _launch_photoshop(ps_exe: str) -> None:
    DETACHED = 0x00000008
    proc = subprocess.Popen([ps_exe], creationflags=DETACHED, close_fds=True)
    print(f"  [+] Launched Photoshop (PID {proc.pid})")


def _wait_for_com(timeout: int = 90):
    try:
        import win32com.client
    except ImportError:
        print("\n[FATAL] pywin32 not installed. Run:  pip install pywin32\n")
        sys.exit(1)

    print(f"  Waiting for Photoshop COM (up to {timeout}s)…", end="", flush=True)
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        for progid in PS_PROGIDS:
            try:
                app = win32com.client.Dispatch(progid)
                ver = app.Version
                print(f"\n  [+] COM ready: {progid}  version={ver}")
                return app
            except Exception:
                pass
        print(".", end="", flush=True)
        time.sleep(2)
    print()
    return None


def _build_diag_jsx(diag_files: dict) -> str:
    """
    Build a self-contained JSX that tries to write to each diagnostic path.
    Returns the JSX source as a string.
    """
    # Build the list of paths as a JS array literal
    entries = []
    for key, path in diag_files.items():
        # Escape backslashes for JS string
        js_path = path.replace("\\", "\\\\")
        entries.append(f'  {{ key: "{key}", path: "{js_path}" }}')
    paths_js = "[\n" + ",\n".join(entries) + "\n]"

    jsx = r"""
app.displayDialogs = DialogModes.NO;

(function() {
  var paths = """ + paths_js + r""";
  var results = [];

  function tryWrite(key, path) {
    try {
      // Ensure parent folder exists
      var parentPath = path.replace(/\\/g, "/");
      var lastSlash = parentPath.lastIndexOf("/");
      if (lastSlash > 0) {
        var parentDir = new Folder(parentPath.substring(0, lastSlash));
        if (!parentDir.exists) parentDir.create();
      }
      var f = new File(path);
      f.encoding = "UTF-8";
      f.open("w");
      f.writeln("ps_diag OK | key=" + key + " | path=" + path + " | " + new Date().toString());
      f.close();
      // Verify it was written
      var f2 = new File(path);
      if (f2.exists && f2.length > 0) {
        results.push("OK:" + key + ":" + path);
      } else {
        results.push("FAIL_VERIFY:" + key + ":" + path);
      }
    } catch(e) {
      results.push("FAIL_EXCEPTION:" + key + ":" + path + ":" + e.message);
    }
  }

  for (var i = 0; i < paths.length; i++) {
    tryWrite(paths[i].key, paths[i].path);
  }

  // Return results as newline-separated string so Python can read it
  return results.join("\n");
})();
"""
    return jsx


# ───────────────────────────────────────────────────────────────────────────
# Main diagnostic
# ───────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  ps-agent-mvp  —  Photoshop Diagnostic Tool")
    print("=" * 60)

    # 1. Find Photoshop.exe ───────────────────────────────────────────────────
    if len(sys.argv) >= 2:
        ps_exe = sys.argv[1]
    else:
        ps_exe = _find_ps_exe()

    if not ps_exe or not Path(ps_exe).exists():
        print(f"\n[FATAL] Photoshop.exe not found: '{ps_exe}'")
        print("  Set 'photoshop_exe' in configjson/example_job.json")
        print("  or pass the path as:  python ps_diag.py \"C:\\path\\to\\Photoshop.exe\"")
        sys.exit(1)

    print(f"\n[1] Photoshop.exe : {ps_exe}")

    # 2. Ensure project out/ exists ──────────────────────────────────────────
    (REPO_ROOT / "out").mkdir(exist_ok=True)

    # 3. Kill + launch Photoshop ─────────────────────────────────────────────
    print("\n[2] Launching Photoshop…")
    _kill_photoshop()
    _launch_photoshop(ps_exe)

    # 4. Wait for COM ────────────────────────────────────────────────────────
    print("\n[3] Connecting via COM…")
    app = _wait_for_com(timeout=90)
    if app is None:
        print("\n[FATAL] Photoshop COM not available after 90s.")
        print("  This portable build may not register a COM server.")
        print("  The pipeline CANNOT work with this Photoshop build.")
        sys.exit(1)

    # 5. Run diagnostic JSX ──────────────────────────────────────────────────
    print("\n[4] Running diagnostic JSX via DoJavaScript…")
    jsx_source = _build_diag_jsx(DIAG_FILES)

    jsx_result = ""
    try:
        try:
            app.DisplayDialogs = 3
        except Exception:
            pass
        jsx_result = app.DoJavaScript(jsx_source, [], 1) or ""
        print(f"  DoJavaScript() returned: {jsx_result!r}")
    except Exception as exc:
        print(f"  [ERROR] DoJavaScript() raised: {exc}")

    # 6. Check which files were created ──────────────────────────────────────
    print("\n[5] Checking diagnostic files…")
    created = []
    missing = []

    for key, path in DIAG_FILES.items():
        p = Path(path)
        if p.exists() and p.stat().st_size > 0:
            created.append((key, path))
            print(f"  OK   : {path}")
        else:
            missing.append((key, path))
            print(f"  MISS : {path}")

    # 7. Interpret results ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  DIAGNOSTIC RESULT")
    print("=" * 60)

    total = len(DIAG_FILES)
    n_ok  = len(created)

    if n_ok == 0:
        print("""
VERDICT: FAIL — Photoshop wrote ZERO files.

This portable Photoshop build completely blocks file I/O from
ExtendScript when executed via COM DoJavaScript().

Options:
  A) Try running task_simple.jsx manually:
       Open Photoshop → File → Scripts → Browse → scripts/task_simple.jsx
     If that creates out/jsx_ok.txt, the issue is specific to COM mode.
     In that case, a different launch method is needed.

  B) Use an officially installed Photoshop (from Adobe Creative Cloud).
     Official builds register COM properly and allow full file I/O.

  C) Use a different automation approach (e.g. UXP plugins, PS Actions).
""")
    elif n_ok < total:
        print(f"\nVERDICT: PARTIAL — {n_ok}/{total} paths writable.\n")
        print("Writable paths:")
        for key, path in created:
            print(f"  + {path}")
        print("\nBlocked paths:")
        for key, path in missing:
            print(f"  - {path}")
        print("""
This means Photoshop CAN write files, but only to certain directories.
The pipeline should work if the output path is in a writable location.

Action: update 'export.png.path' in configjson/example_job.json to use
one of the writable paths shown above.
""")
    else:
        print(f"""
VERDICT: PASS — All {total}/{total} diagnostic files created successfully!

Photoshop can write files via COM DoJavaScript.
The pipeline should work. If final.png is still not created, the issue
is in task.jsx logic (config path, base image, layer placement, export).

Next step: run the full pipeline:
  python orchestrator.py configjson/example_job.json

Then check:
  out\\example_job\\run.log     — JSX execution log
  out\\bootstrap.log           — early JSX startup log
  out\\example_job\\final.png  — the output image
""")

    # Clean up diagnostic files
    print("[6] Cleaning up diagnostic files…")
    for key, path in created:
        try:
            Path(path).unlink()
            print(f"  Removed: {path}")
        except Exception:
            pass

    print("\nDiagnostic complete.")


if __name__ == "__main__":
    main()
