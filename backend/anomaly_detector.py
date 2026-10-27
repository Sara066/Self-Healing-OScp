"""
Phase 5 — Anomaly detector

Thin wrapper around scikit-learn's IsolationForest. Fit ONLY on normal
ticks (training_normal.csv from Phase 4) so it learns what typical
(CPU%, queue length, wait, thread count, memory%, fault rate) tuples look
like; score() then flags any tick whose feature combination falls outside
that learned region.

Deliberately not hand-implemented — it's a scikit-learn primitive, not
something the syllabus asks you to build from scratch.
"""

import pandas as pd
from sklearn.ensemble import IsolationForest

ROLL_WINDOW = 5

FEATURE_COLS = ["cpu_pct", "queue_total", "avg_wait",
                "thread_count_running", "mem_used_pct", "page_faults_tick",
                "pid_dominance", "mem_used_pct_roll", "page_faults_roll"]


def add_rolling_features(df: pd.DataFrame, window: int = ROLL_WINDOW) -> pd.DataFrame:
    """
    Rolling mean of the two noisiest per-tick signals, grouped by run_id so
    a window never bleeds across two different simulation runs.

    A single tick can look "normal" purely by chance -- e.g. a thrashing
    process momentarily touches a resident page and has 0 faults that
    exact tick, even though it's genuinely thrashing overall. Scoring raw
    per-tick values caps recall around a third of anomalous ticks, since
    on any given tick roughly two-thirds of them just aren't extreme
    enough to clear the threshold on their own. Smoothing over the last
    few ticks makes the sustained pattern visible instead of drowning it
    in that tick-level noise.
    """
    df = df.copy()
    df["mem_used_pct_roll"] = (
        df.groupby("run_id")["mem_used_pct"]
          .transform(lambda s: s.rolling(window, min_periods=window).mean())
    )
    df["page_faults_roll"] = (
        df.groupby("run_id")["page_faults_tick"]
          .transform(lambda s: s.rolling(window, min_periods=window).mean())
    )
    # first (window-1) ticks of each run have no full window yet -- fall
    # back to the raw same-tick value rather than leaving NaN
    df["mem_used_pct_roll"] = df["mem_used_pct_roll"].fillna(df["mem_used_pct"])
    df["page_faults_roll"] = df["page_faults_roll"].fillna(df["page_faults_tick"])
    return df


class AnomalyDetector:
    def __init__(self, contamination: float = 0.05, random_state: int = 42):
        self.model = IsolationForest(contamination=contamination,
                                      random_state=random_state,
                                      n_estimators=150)
        self.feature_cols = FEATURE_COLS

    def fit(self, df_normal: pd.DataFrame) -> "AnomalyDetector":
        self.model.fit(df_normal[self.feature_cols])
        return self

    def score(self, df: pd.DataFrame) -> pd.DataFrame:
        """Adds anomaly_score (higher = more abnormal) and is_anomaly (bool)."""
        df = df.copy()
        raw = self.model.decision_function(df[self.feature_cols])  # higher = more normal
        pred = self.model.predict(df[self.feature_cols])           # -1 = anomaly
        df["anomaly_score"] = -raw
        df["is_anomaly"] = pred == -1
        return df

    def score_tick(self, feature_row: dict) -> tuple:
        """Score a single live tick (used by run_scenarios.py in Phase 6)."""
        import pandas as pd
        row_df = pd.DataFrame([feature_row])[self.feature_cols]
        score = -self.model.decision_function(row_df)[0]
        is_anom = self.model.predict(row_df)[0] == -1
        return score, bool(is_anom)