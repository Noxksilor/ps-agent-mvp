import json, os, shutil, time
from pathlib import Path

JOB = Path(r"C:\ps_jobs\job_0001")
OUTPUT = JOB / "output"
ITERS = JOB / "iterations"

def main():
    OUTPUT.mkdir(exist_ok=True)
    ITERS.mkdir(exist_ok=True)
    cfg = json.loads((JOB/"config.json").read_text(encoding="utf-8"))
    print("OK: config loaded. layers =", len(cfg.get("layers", [])))
    (OUTPUT/"run.log").write_text("MVP: orchestrator стартовал\\n", encoding="utf-8")
    print("Wrote", OUTPUT/"run.log")

if __name__ == "__main__":
    main()
