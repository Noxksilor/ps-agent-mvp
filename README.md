# ps-agent-mvp

Automated Photoshop compositing pipeline with a single Python entrypoint.

```
python orchestrator.py configjson/example_job.json
```

---

## How it works

```
orchestrator.py
    │
    ├─ reads  configjson/<job>.json          ← job config (paths, layers, export)
    ├─ writes config.json (repo root)        ← runtime copy for JSX
    │
    ├─ launches  scripts/launch_ps.ahk       ← AutoHotkey wrapper
    │               └─ Photoshop.exe -r scripts/task.jsx
    │                       └─ reads config.json
    │                       └─ composites layers
    │                       └─ saves  out/<job_id>/final.png
    │
    └─ polls  out/<job_id>/final.png         ← waits up to timeout_seconds
         ├─ SUCCESS → exit 0
         └─ TIMEOUT → exit 1
```

Logs are written to `out/<job_id>/run.log` (JSX side) and printed to stdout (Python side).

---

## Repository layout

```
ps-agent-mvp/
├── orchestrator.py          ← single entrypoint
├── config.json              ← runtime config (auto-generated each run, do not edit)
│
├── configjson/              ← per-job configs (tracked in git)
│   └── example_job.json
│
├── scripts/
│   ├── task.jsx             ← ExtendScript run inside Photoshop
│   └── launch_ps.ahk        ← AutoHotkey launcher
│
├── input/                   ← source images (not tracked in git)
│   ├── base.png
│   └── asset_01.png
│
└── out/                     ← output PNGs and logs (not tracked in git)
    └── <job_id>/
        ├── final.png
        └── run.log
```

---

## Requirements

| Requirement | Notes |
|---|---|
| **Windows** | Photoshop is Windows-only |
| **Python 3.8+** | One third-party package needed (see below) |
| **pywin32** | `pip install pywin32` — used to drive Photoshop via COM |
| **Adobe Photoshop** | Any version, including portable builds |

> **Why pywin32?**
> The `-r` flag (`Photoshop.exe -r script.jsx`) only works with officially
> installed Photoshop. Portable builds ignore it. The orchestrator instead
> launches Photoshop normally and then calls `app.DoScript()` via Windows COM,
> which works with any build.

---

## Step-by-step setup

### 1. Clone the repo

```bat
git clone https://github.com/your-org/ps-agent-mvp.git
cd ps-agent-mvp
```

### 2. Install AutoHotkey

Download from <https://www.autohotkey.com/> and install.  
Verify it is on PATH:

```bat
autohotkey.exe /? 
```

### 3. Prepare input images

Place your source images in the `input/` folder:

```
input/
├── base.png        ← background / base layer
└── asset_01.png    ← overlay asset
```

### 4. Create (or edit) a job config

Copy `configjson/example_job.json` and adjust:

```jsonc
{
  "job_id": "my_job",

  // Full path to your Photoshop executable
  "photoshop_exe": "C:\\Program Files\\Adobe\\Adobe Photoshop 2024\\Photoshop.exe",

  "canvas": { "width": 1080, "height": 1080, "dpi": 72, "background": "transparent" },

  "base": { "path": "input/base.png" },

  "layers": [
    {
      "name": "asset_01",
      "type": "image",
      "path": "input/asset_01.png",
      "transform": { "x": 540, "y": 540, "scale": 80, "rotate": 0 }
    }
  ],

  "export": {
    "png": { "path": "out/my_job/final.png" },
    "psd": { "enabled": false, "path": "out/my_job/final.psd" }
  },

  // How long (seconds) to wait for Photoshop to finish
  "timeout_seconds": 120
}
```

Key fields:

| Field | Description |
|---|---|
| `job_id` | Identifier used in log messages |
| `photoshop_exe` | Absolute path to `Photoshop.exe` |
| `base.path` | Path to the background image, relative to repo root |
| `layers[].path` | Path to each overlay asset, relative to repo root |
| `layers[].transform` | `x`, `y` = centre position (px); `scale` = % of original size; `rotate` = degrees |
| `export.png.path` | Where to write the final PNG, relative to repo root |
| `timeout_seconds` | Abort if PNG not created within this many seconds |

### 5. Run the pipeline

```bat
python orchestrator.py configjson/example_job.json
```

Expected output:

```
2026-02-18 10:00:00 | INFO    | ============================================================
2026-02-18 10:00:00 | INFO    | Job      : example_job
2026-02-18 10:00:00 | INFO    | Config   : C:\...\configjson\example_job.json
2026-02-18 10:00:00 | INFO    | Output   : C:\...\out\example_job\final.png
2026-02-18 10:00:00 | INFO    | JSX      : C:\...\scripts\task.jsx
2026-02-18 10:00:00 | INFO    | Wrote runtime config.json → C:\...\config.json
2026-02-18 10:00:00 | INFO    | Launching: "AutoHotkey.exe" "...\launch_ps.ahk" "...\Photoshop.exe" "...\task.jsx"
2026-02-18 10:00:00 | INFO    | Waiting up to 120s for final.png …
2026-02-18 10:00:15 | INFO    | SUCCESS — final.png created (312.4 KB, 15.2s elapsed)
```

Exit code `0` = success, `1` = error.

### 6. Find the output

```
out/
└── example_job/
    ├── final.png   ← composited image
    └── run.log     ← detailed JSX-side log
```

---

## Troubleshooting

### "AutoHotkey not found on PATH"

Add the AutoHotkey installation folder to your system `PATH`, or pass the full path by editing `orchestrator.py` → `_find_ahk()`.

### "Photoshop.exe not found"

Set the correct path in your job config under `photoshop_exe`.

### Timeout — `final.png` not created

1. Open `out/<job_id>/run.log` — the JSX writes detailed errors there.
2. Also check `out/bootstrap.log` for very early JSX errors.
3. Common causes:
   - `input/base.png` is missing.
   - Photoshop shows a dialog (license, update) — dismiss it and re-run.
   - Photoshop version does not support the `-r` flag — try opening PS manually and running the script via **File → Scripts → Browse**.

### Running without AutoHotkey

If you prefer to launch Photoshop manually, you can skip AHK entirely:

1. Open Photoshop.
2. **File → Scripts → Browse** → select `scripts/task.jsx`.
3. The orchestrator will still detect the output PNG if it is already polling.

Alternatively, call Photoshop directly from Python by setting `photoshop_exe` and removing the AHK step — edit `orchestrator.py` → `run_pipeline()` and replace the AHK `subprocess.Popen` call with:

```python
subprocess.Popen([str(ps_exe), "-r", str(TASK_JSX)], cwd=str(REPO_ROOT))
```

---

## Adding more jobs

1. Create `configjson/my_new_job.json` (copy from `example_job.json`).
2. Run: `python orchestrator.py configjson/my_new_job.json`

Each job gets its own output folder `out/<job_id>/`.

---

## Architecture overview

```
┌─────────────────────────────────────────────────────────────┐
│  orchestrator.py  (Python, cross-platform logic)            │
│                                                             │
│  1. parse CLI arg → load configjson/<job>.json              │
│  2. validate: PS exe, task.jsx, AHK on PATH                 │
│  3. write runtime config.json (repo root)                   │
│  4. subprocess → AutoHotkey → Photoshop -r task.jsx         │
│  5. poll out/<job_id>/final.png  (1 s interval)             │
│  6. log result, exit 0/1                                    │
└──────────────────────────┬──────────────────────────────────┘
                           │ launches
┌──────────────────────────▼──────────────────────────────────┐
│  scripts/launch_ps.ahk  (AutoHotkey v1)                     │
│                                                             │
│  • receives: <photoshop_exe> <jsx_path>                     │
│  • runs:  Photoshop.exe -r task.jsx  (hidden window)        │
│  • exits after 2 s hand-off delay                           │
└──────────────────────────┬──────────────────────────────────┘
                           │ runs inside Photoshop
┌──────────────────────────▼──────────────────────────────────┐
│  scripts/task.jsx  (Adobe ExtendScript)                     │
│                                                             │
│  • reads  config.json  (repo root)                          │
│  • opens  input/base.png                                    │
│  • places each layer from config                            │
│  • exports  out/<job_id>/final.png                          │
│  • writes   out/<job_id>/run.log                            │
└─────────────────────────────────────────────────────────────┘
```
