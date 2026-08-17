from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(r"C:\Users\demos\OneDrive\Documents\ChatGPT\Scrap AI\research")
INPUTS = ROOT / "inputs" / "external"
OUTPUTS = ROOT / "outputs"
AS_OF = pd.Timestamp("2026-08-11")


def yield_midpoint(vessel_type: str) -> tuple[str, float]:
    name = str(vessel_type).upper()
    if "TANKER" in name or "LNG" in name or "LPG" in name:
        return "tanker", 0.765
    if "BULK" in name:
        return "bulker", 0.66
    if "CONTAINER" in name:
        return "container", 0.65
    if any(token in name for token in ["CARGO", "RORO", "RO-RO"]):
        return "general_cargo", 0.63
    if any(token in name for token in ["PLATFORM", "RIG", "DRILL", "BARGE"]):
        return "special_structure", 0.35
    return "other", 0.60


def gamma_cdf_integer_shape3(age_days: np.ndarray, theta: float) -> np.ndarray:
    x = np.maximum(age_days, 0) / theta
    return 1.0 - np.exp(-x) * (1.0 + x + x * x / 2.0)


def main() -> None:
    files = sorted(INPUTS.glob("alangtoday_demolition_current_*.csv"))
    if not files:
        raise FileNotFoundError("Current Alang demolition snapshot missing")
    ships = pd.read_csv(files[-1])
    ships["beached_date"] = pd.to_datetime(ships["beached_date_source_text"], errors="coerce", dayfirst=True)
    ships["ldt"] = pd.to_numeric(ships["ldt_metric_tonnes"], errors="coerce")
    ships["age_days"] = (AS_OF - ships["beached_date"]).dt.days
    mapped = ships["vessel_type"].map(yield_midpoint)
    ships["yield_class"] = mapped.map(lambda x: x[0])
    ships["yield_midpoint"] = mapped.map(lambda x: x[1])
    ships["plate_potential_t"] = ships["ldt"] * ships["yield_midpoint"]

    scenario_rows = []
    for theta in [30.0, 45.0]:
        for horizon in [30, 45, 60, 90]:
            age = ships["age_days"].to_numpy(float)
            now_cdf = gamma_cdf_integer_shape3(age, theta)
            future_cdf = gamma_cdf_integer_shape3(age + horizon, theta)
            incremental = ships["plate_potential_t"].to_numpy(float) * (future_cdf - now_cdf)
            valid = np.isfinite(incremental) & (age >= 0) & (age <= 365)
            scenario_rows.append({
                "as_of": str(AS_OF.date()),
                "kernel_shape": 3,
                "kernel_theta_days": int(theta),
                "kernel_mode_days": int(2 * theta),
                "forward_window_days": horizon,
                "snapshot_vessels_age_0_365": int(valid.sum()),
                "estimated_incremental_plate_release_t": float(np.nansum(incremental[valid])),
                "status": "FORWARD-ONLY SCENARIO; NOT BACKTESTED",
            })

    age_rows = []
    for days in [30, 60, 90, 120, 180, 365]:
        recent = ships[ships["age_days"].between(0, days)]
        age_rows.append({
            "as_of": str(AS_OF.date()),
            "lookback_days": days,
            "vessels_in_snapshot": int(len(recent)),
            "ldt_t": float(recent["ldt"].sum()),
            "plate_potential_t": float(recent["plate_potential_t"].sum()),
        })

    ships.to_csv(OUTPUTS / "live_vessel_inventory_detail.csv", index=False)
    pd.DataFrame(scenario_rows).to_csv(OUTPUTS / "live_supply_release_scenarios.csv", index=False)
    pd.DataFrame(age_rows).to_csv(OUTPUTS / "live_supply_recent_beachings.csv", index=False)
    metadata = {
        "as_of": str(AS_OF.date()),
        "source_snapshot": files[-1].name,
        "government_yield_midpoints": {
            "general_cargo": 0.63,
            "bulker": 0.66,
            "tanker": 0.765,
            "container": 0.65,
            "special_structure_assumption": 0.35,
            "other_assumption": 0.60,
        },
        "release_kernel": "Gamma shape 3; theta 30 and 45-day sensitivities; mode 60 and 90 days",
        "warning": "The 70-row public table is a current-state snapshot, not a complete arrivals archive. Yield and kernel values are scenario priors. These numbers contextualize the live 45-90 day supply risk and are not validated forecasts.",
    }
    (OUTPUTS / "live_supply_inventory_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(pd.DataFrame(age_rows).to_string(index=False))
    print(pd.DataFrame(scenario_rows).to_string(index=False))


if __name__ == "__main__":
    main()
