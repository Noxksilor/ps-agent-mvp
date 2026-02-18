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

## One-click start (Windows + Docker Desktop)

The fastest way to get the full stack running — Photoshop pipeline **+** n8n automation UI — is the included PowerShell launcher:

```powershell
.\start_ps_agent.ps1
```

### What the script does

| Step | Action |
|---|---|
| 1 | Checks if Docker Desktop is running; starts it automatically if not |
| 2 | Waits until the Docker daemon is ready (up to 120 s) |
| 3 | Runs `docker compose up -d` to start the n8n container |
| 4 | Waits until n8n is reachable at `http://localhost:5678` (up to 90 s) |
| 5 | *(Optional)* Activates a specific n8n workflow via the REST API |
| 6 | Opens `http://localhost:5678` in your default browser |

### First-time setup

1. **Install Docker Desktop** from <https://www.docker.com/products/docker-desktop/>.
   Enable "Start Docker Desktop when you log in" in Settings → General.

2. **Clone the repo** and enter the project folder:
   ```bat
   git clone https://github.com/Noxksilor/ps-agent-mvp.git
   cd ps-agent-mvp
   ```

3. **Install Python dependencies** (one-time):
   ```bat
   pip install pywin32
   ```

4. **Configure your job** in `configjson/example_job.json`:
   - Set `photoshop_exe` to your Photoshop path.
   - Set `export.png.path` to a writable absolute path (run `python ps_diag.py` to find one).

5. **Run the launcher**:
   ```powershell
   .\start_ps_agent.ps1
   ```
   The browser will open `http://localhost:5678` automatically.

### Auto-activating a workflow (optional)

To have the script automatically activate an n8n workflow on startup:

1. Import your workflow into n8n.
2. Open the workflow in the n8n UI — the URL will look like:
   `http://localhost:5678/workflow/abc123`
3. Copy the ID (`abc123`).
4. Edit `start_ps_agent.ps1` and set:
   ```powershell
   $WorkflowId = "abc123"
   ```

The script will call `PATCH /api/v1/workflows/<id>` with `{"active":true}` on every startup.

### Stopping the stack

```bat
docker compose down
```

---

## Requirements

| Requirement | Notes |
|---|---|
| **Windows** | Photoshop is Windows-only |
| **Python 3.8+** | One third-party package needed (see below) |
| **pywin32** | `pip install pywin32` — used to drive Photoshop via COM |
| **Adobe Photoshop** | Any version, including portable builds |
| **Docker Desktop** | Required only for n8n; not needed for the Photoshop pipeline alone |

> **Why pywin32?**
> The `-r` flag (`Photoshop.exe -r script.jsx`) only works with officially
> installed Photoshop. Portable builds ignore it. The orchestrator instead
> launches Photoshop normally and then calls `app.DoJavaScript()` via Windows COM,
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
    ├── final.png   ← composited image (copied here from JSX output path)
    └── run.log     ← detailed JSX-side log
```

> **Note on output paths:**
> Some Photoshop builds (portable) can only write files to certain directories
> (e.g. `C:\Users\Public\`). In that case, set `export.png.path` in your job
> config to an absolute writable path:
>
> ```json
> "export": {
>   "png": { "path": "C:/Users/Public/ps_agent_example_job.png" }
> }
> ```
>
> The orchestrator will poll that path and automatically **copy** the result
> to `out/<job_id>/final.png` when it appears. The user-facing output is
> always `out/<job_id>/final.png` regardless of where JSX writes.

---

## Diagnostics

Before running the full pipeline, use the diagnostic tool to verify that your Photoshop build can execute JSX and write files:

```bat
python ps_diag.py
```

Or with an explicit path:

```bat
python ps_diag.py "C:\Users\User\Documents\Zona Downloads\Photoshop\Photoshop.exe"
```

### What it tests

The script launches Photoshop, connects via COM, and runs a minimal JSX that tries to write to **four different locations**:

| Test file | Location |
|---|---|
| `C:\ps_diag_root.txt` | Root of C: drive |
| `C:\Users\Public\ps_diag_public.txt` | Public user folder |
| `<repo>\out\jsx_diag.txt` | Project output folder |
| `%TEMP%\ps_diag_temp.txt` | Windows TEMP folder |

### How to interpret the result

| Result | Meaning | Action |
|---|---|---|
| **PASS** — all 4 files created | Photoshop + COM + JSX file I/O all work | Run `python orchestrator.py configjson/example_job.json` |
| **PARTIAL** — some files created | PS can write, but only to certain paths | Move output path to a writable location |
| **FAIL** — zero files created | This PS build blocks all JSX file I/O via COM | Try manual test (see below) or use official PS |

### Manual JSX test (if FAIL)

Open Photoshop, then:
**File → Scripts → Browse** → select `scripts/task_simple.jsx`

- If `out/jsx_ok.txt` appears → JSX works manually but not via COM. The issue is COM-specific.
- If nothing appears → this Photoshop build cannot run ExtendScript at all.

---

## Troubleshooting

### "Photoshop.exe not found"

Set the correct path in your job config under `photoshop_exe`.

### Timeout — `final.png` not created

1. Run `python ps_diag.py` first to confirm JSX file I/O works.
2. Open `out/<job_id>/run.log` — the JSX writes detailed errors there.
3. Also check `out/bootstrap.log` for very early JSX errors.
4. Check `out/jsx_debug.txt` — if it exists, JSX started successfully.
5. Common causes:
   - `input/base.png` is missing.
   - Photoshop shows a dialog (license, update) — dismiss it and re-run.
   - Portable Photoshop build blocks file I/O via COM.

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
