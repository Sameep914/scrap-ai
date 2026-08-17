from __future__ import annotations

"""Fixed six-model 8ANI test using the audited v3 walk-forward machinery."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

import forecast_study_v3 as core


OUTPUTS = core.ROOT / "outputs" / "simple_model_test"
OUTPUTS.mkdir(parents=True, exist_ok=True)

# Frozen before the run.  Each candidate is deliberately sparse and causal.
MODEL_FEATURES = {
    "plate_melt_z": ["plate_melt_z60"],
    "own_momentum": ["own_mom_10d"],
    "local_ingot_tmt": ["local_ingot_mom10", "local_tmt_mom10"],
    "turkey_momentum": ["turkey_mom10"],
    "plate_melt_local": ["plate_melt_z60", "local_ingot_mom10", "local_tmt_mom10"],
    "plate_melt_turkey": ["plate_melt_z60", "turkey_mom10"],
}


def main() -> None:
    # Reuse the audited definitions for strict-prior joins, calendar targets,
    # purging, expanding training, fold-only preprocessing, and loss metrics.
    core.MODEL_FEATURES = MODEL_FEATURES
    core.MODEL_ORDER = list(MODEL_FEATURES)
    core.COMBINED_FEATURES = sorted({name for names in MODEL_FEATURES.values() for name in names})
    core.BOOTSTRAP_REPS = 2000
    core.MAX_NULL_REPS = 2000
    core.RNG = np.random.default_rng(core.SEED + 91)

    panel, audit = core.build_panel()
    panel = core.add_targets(panel)

    origin_counts: dict[str, int] = {}
    parts: list[pd.DataFrame] = []
    for horizon in core.HORIZONS:
        origins = core.common_origins(panel, horizon)
        origin_counts[str(horizon)] = int(len(origins))
        for model in core.MODEL_ORDER:
            parts.append(core.backtest_model(panel, horizon, model, origins))
            print(f"tested horizon={horizon} model={model} n={len(origins)}", flush=True)

    predictions = pd.concat(parts, ignore_index=True)
    for horizon in core.HORIZONS:
        groups = [
            predictions[(predictions["horizon"] == horizon) & (predictions["model"] == model)]
            .sort_values("origin_date")["origin_date"]
            .reset_index(drop=True)
            for model in core.MODEL_ORDER
        ]
        assert all(groups[0].equals(item) for item in groups[1:])

    predictions = core.add_point_in_time_calls(predictions)
    phases = core.phase_offset_stability(predictions)
    summary = core.summarize_predictions(predictions, phases)
    mae_adj, mae_meta = core.max_null_adjustment(predictions, "mae_skill_zero")
    brier_adj, brier_meta = core.max_null_adjustment(predictions, "brier_skill_frequency")
    adjustment = pd.concat([mae_adj, brier_adj], ignore_index=True)
    live = core.fit_live_forecasts(panel, summary, adjustment)

    # A compact ranking used for handoff; positive skill means beating the stated baseline.
    ranked = summary.merge(
        adjustment[["metric", "horizon", "model", "max_null_adjusted_p"]],
        on=["horizon", "model"],
        how="left",
    )

    panel.to_csv(OUTPUTS / "panel.csv", index=False)
    predictions.to_csv(OUTPUTS / "oos_predictions.csv", index=False)
    phases.to_csv(OUTPUTS / "phase_stability.csv", index=False)
    summary.to_csv(OUTPUTS / "summary.csv", index=False)
    adjustment.to_csv(OUTPUTS / "max_null_adjustment.csv", index=False)
    ranked.to_csv(OUTPUTS / "ranked_metrics.csv", index=False)
    live.to_csv(OUTPUTS / "live_forecasts.csv", index=False)

    metadata = {
        "models": MODEL_FEATURES,
        "horizons_calendar_days": core.HORIZONS,
        "target_tolerance_days": core.TARGET_TOLERANCE_DAYS,
        "strict_prior_external_joins": True,
        "same_origins_within_horizon": True,
        "purge": "target_end strictly before origin",
        "walk_forward": "expanding",
        "oos_origin_spacing_days": core.OOS_ORIGIN_SPACING_DAYS,
        "magnitude_baseline": "zero change",
        "direction_baseline": "expanding Laplace-smoothed class frequency",
        "bootstrap_reps": core.BOOTSTRAP_REPS,
        "max_null_reps": core.MAX_NULL_REPS,
        "candidate_count": len(MODEL_FEATURES) * len(core.HORIZONS),
        "origin_counts": origin_counts,
        "data_audit": audit,
        "mae_max_null": mae_meta,
        "brier_max_null": brier_meta,
    }
    (OUTPUTS / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
