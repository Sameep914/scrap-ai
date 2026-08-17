from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(r"C:\Users\demos\OneDrive\Documents\ChatGPT\Scrap AI\research")
INPUTS = ROOT / "inputs"
OUTPUTS = ROOT / "outputs"
RNG = np.random.default_rng(20260812)


def load_monthly() -> pd.DataFrame:
    files = sorted((INPUTS / "external").glob("alangtoday_monthly_beachings_2016_2026_asof_*.csv"))
    if not files:
        raise FileNotFoundError("AlangToday monthly snapshot not found")
    raw = pd.read_csv(files[-1])
    print(raw.columns.tolist())
    return raw


def load_mandi_monthly() -> pd.DataFrame:
    data = pd.read_csv(INPUTS / "mandi_master.csv")
    data["date"] = pd.to_datetime(data["Date"], errors="coerce")
    data["8ANI"] = pd.to_numeric(data["8ANI"], errors="coerce")
    data = data.dropna(subset=["date", "8ANI"]).sort_values("date")
    data["month"] = data["date"].dt.to_period("M")
    return data.groupby("month").agg(price=("8ANI", "last"), avg_price=("8ANI", "mean"), quotes=("8ANI", "size")).reset_index()


def main() -> None:
    raw = load_monthly()
    # Flexible schema from the point-in-time snapshot.
    colmap = {c.lower().strip(): c for c in raw.columns}
    date_col = next(c for c in raw.columns if "month" in c.lower() or "date" in c.lower())
    ldt_col = next(c for c in raw.columns if "ldt" in c.lower())
    ship_col = next((c for c in raw.columns if "ship" in c.lower() and "source" not in c.lower()), None)
    supply = raw.copy()
    supply["month"] = pd.to_datetime(supply[date_col], errors="coerce").dt.to_period("M")
    supply["ldt"] = pd.to_numeric(supply[ldt_col].astype(str).str.replace(",", "", regex=False), errors="coerce")
    supply["ships"] = pd.to_numeric(supply[ship_col], errors="coerce") if ship_col else np.nan
    supply = supply.dropna(subset=["month"]).sort_values("month").drop_duplicates("month", keep="last")
    mandi = load_mandi_monthly()
    merged = mandi.merge(supply[["month", "ldt", "ships"]], on="month", how="left").sort_values("month")
    for lag in [1, 2, 3]:
        merged[f"ldt_lag{lag}"] = merged["ldt"].shift(lag)
        merged[f"ships_lag{lag}"] = merged["ships"].shift(lag)
        merged[f"fwd_ret{lag}m"] = np.log(merged["price"].shift(-lag) / merged["price"])

    rows = []
    for factor in ["ldt", "ships"]:
        for lag in [1, 2, 3]:
            x = merged[factor]
            y = merged[f"fwd_ret{lag}m"]
            valid = x.notna() & y.notna()
            if valid.sum() < 5:
                continue
            corr = float(np.corrcoef(x[valid], y[valid])[0, 1])
            # Leave-one-month-out sensitivity: no p-value claims at this sample size.
            loo = []
            ids = np.flatnonzero(valid.to_numpy())
            for idx in ids:
                keep = valid.to_numpy().copy()
                keep[idx] = False
                loo.append(float(np.corrcoef(x[keep], y[keep])[0, 1]))
            rows.append({
                "factor": factor,
                "lead_months": lag,
                "n": int(valid.sum()),
                "correlation": corr,
                "loo_corr_min": min(loo),
                "loo_corr_median": float(np.median(loo)),
                "loo_corr_max": max(loo),
                "status": "CONTEXT ONLY - current-vintage series, unknown historical release timestamps",
            })

    out = pd.DataFrame(rows)
    merged.to_csv(OUTPUTS / "monthly_supply_context_panel.csv", index=False)
    out.to_csv(OUTPUTS / "monthly_supply_context_results.csv", index=False)
    meta = {
        "warning": "AlangToday monthly history was captured as a 2026-08-12 current-vintage page. Original month-by-month publication timestamps and revisions are unknown; these correlations are descriptive only and cannot be called point-in-time forecasts.",
        "mandi_months": int(len(mandi)),
        "overlap_months_with_supply": int(merged["ldt"].notna().sum()),
        "tested_candidates": int(len(out)),
    }
    (OUTPUTS / "monthly_supply_context_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(out.to_string(index=False))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
