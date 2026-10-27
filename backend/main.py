"""
FastAPI wrapper around the existing self-healing OS simulation.

Nothing about scheduler.py / memory_manager.py / anomaly_detector.py /
diagnosis.py / recovery.py / verifier.py changes. This file just:
  1. trains the anomaly detector once at startup (not per-request)
  2. exposes POST /api/run/{scenario} which builds a process list,
     runs run_live_scenario() (or run_deadlock_scenario()) exactly the
     way run_scenarios.py's main() does, and returns the result as JSON
  3. serves the frontend's static files

Run with:  uvicorn main:app --reload --port 8000
Then open: http://127.0.0.1:8000
"""

import json
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from anomaly_injection import normal_scenario, inject_runaway, inject_thrashing, inject_abnormal_combo
from anomaly_detector import AnomalyDetector, add_rolling_features
from diagnosis import build_normal_stats
from run_scenarios import run_live_scenario, run_deadlock_scenario

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

app = FastAPI(title="Self-Healing OS API")

# ---- train the detector once, at process startup -------------------------
_train_df = add_rolling_features(pd.read_csv(BASE_DIR / "training_normal.csv"))
_detector = AnomalyDetector(contamination=0.05).fit(_train_df)
_normal_stats = build_normal_stats(_train_df)

# scenario name -> (builder(seed) -> list[PCB], injected_pid)
SCENARIO_BUILDERS = {
    "normal": lambda seed: (normal_scenario(seed=seed), None),
    "runaway": lambda seed: (inject_runaway(normal_scenario(seed=seed), pid=99), 99),
    "thrashing": lambda seed: (inject_thrashing(normal_scenario(seed=seed), pid=88), 88),
    "abnormal_combo": lambda seed: (inject_abnormal_combo(normal_scenario(seed=seed), pid=77), 77),
}


class RunRequest(BaseModel):
    seed: int = 999
    num_frames: int = 32


@app.get("/api/scenarios")
def list_scenarios():
    return {"scenarios": list(SCENARIO_BUILDERS.keys()) + ["deadlock"]}


@app.post("/api/run/{scenario}")
def run_scenario(scenario: str, req: RunRequest):
    if scenario == "deadlock":
        summary, narrative = run_deadlock_scenario()
        return {"scenario": "deadlock", "summary": summary, "narrative": narrative, "ticks": []}

    builder = SCENARIO_BUILDERS.get(scenario)
    if builder is None:
        raise HTTPException(status_code=404, detail=f"unknown scenario '{scenario}'")

    procs, injected_pid = builder(req.seed)
    df, summary, narrative = run_live_scenario(
        scenario, procs, injected_pid, _detector, _normal_stats,
        num_frames=req.num_frames, seed=req.seed,
    )

    # df.to_json handles numpy/pandas dtypes (bool_, int64, NaN) correctly;
    # a plain df.to_dict() trips up FastAPI's default JSON encoder on those.
    ticks = json.loads(df.to_json(orient="records"))

    return {"scenario": scenario, "summary": summary, "narrative": narrative, "ticks": ticks}


# serve the frontend last, so /api/* above always takes priority
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
