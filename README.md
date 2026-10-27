# Self-healing OS — local dashboard

A FastAPI backend around the existing scheduler/memory/anomaly simulation, with a
plain HTML/JS frontend that runs a scenario on demand and visualizes it.

## Project structure

```
project/
├── backend/
│   ├── main.py              # FastAPI app: /api/scenarios, /api/run/{scenario}
│   ├── pcb.py                    ┐
│   ├── scheduler.py              │
│   ├── memory_manager.py         │  unchanged copies of your
│   ├── deadlock.py               │  existing simulation modules
│   ├── anomaly_injection.py      │
│   ├── anomaly_detector.py       │
│   ├── diagnosis.py              │
│   ├── recovery.py               │
│   ├── verifier.py               │
│   ├── run_scenarios.py          ┘
│   ├── training_normal.csv  # used to fit the detector at startup
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js                # fetch()es the backend, renders charts
└── README.md
```

## Run it

```bash
cd backend
python3 -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Then open **http://127.0.0.1:8000** — FastAPI serves the frontend directly, so
there's nothing else to start and no CORS to configure.

Interactive API docs (useful for testing the backend on its own) are at
**http://127.0.0.1:8000/docs**.

## API

`GET /api/scenarios`
→ `{"scenarios": ["normal","runaway","thrashing","abnormal_combo","deadlock"]}`

`POST /api/run/{scenario}`
body: `{"seed": 999, "num_frames": 32}`
→ `{"scenario", "summary", "narrative", "ticks"}`

- `ticks` is the full per-tick log (150 rows) as used by `run_scenarios.py` —
  empty for `deadlock`, which is graph-based and not tick-driven.
- `summary` mirrors one row of `scenario_summary.csv` (detection tick,
  diagnosis, action taken, ticks to recovery).
- `narrative` is the human-readable log line list.

Each call re-runs the scenario from scratch server-side (deterministic given
the same `seed`); nothing is cached or streamed. The frontend requests one
full run and then scrubs/animates through the returned log client-side.

## Notes / things you might want to change

- **CORS / `allow_origins`**: not needed at all right now, since the frontend
  is served from the same FastAPI process. If you ever split them (e.g. a
  separate `npm run dev` server on another port), add
  `fastapi.middleware.cors.CORSMiddleware` in `main.py`.
- **`mlfq.py` and `classic_schedulers.py`** aren't wired into the API — they're
  not used by `run_scenarios.py` either. Easy to add a
  `POST /api/compare-schedulers` endpoint later if you want the Unit 2
  algorithm comparison in the UI too.
- The detector is trained once at import time (module-level in `main.py`), so
  the first request after `uvicorn` starts is not slower than the rest.
