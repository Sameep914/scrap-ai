from __future__ import annotations

"""Predeclared sign rule for the one factor that survived the native screen."""

import math

import numpy as np
import pandas as pd

import forecast_study_v3 as core
import global_factor_test as gf


OUT = core.ROOT / "outputs" / "global_factor_test"
REPS = 5000
RNG = np.random.default_rng(20260812 + 333)


def circular(n: int, block: int) -> np.ndarray:
    out: list[int] = []
    while len(out) < n:
        start = int(RNG.integers(n))
        out.extend(((start + np.arange(block)) % n).tolist())
    return np.asarray(out[:n], int)


def ci(values: np.ndarray, block: int) -> tuple[float, float, float]:
    means = np.asarray([np.mean(values[circular(len(values), block)]) for _ in range(REPS)])
    return float(np.mean(values)), float(np.quantile(means, .025)), float(np.quantile(means, .975))


def main() -> None:
    panel, _ = core.build_panel()
    panel = core.add_targets(panel)
    factor = gf.Factor(
        "china_hrc_weekly_mom1w", gf.weekly_hrc(1), "weekly",
        "audited weekly price; roll method opaque", True, 26, 10, [10, 15],
    )
    frame = gf.attach_factor(panel, factor)
    all_rows = []
    summaries = []
    for horizon in [10, 15]:
        target = f"target_ret_{horizon}"
        valid = frame.dropna(subset=["signal", target, f"target_end_{horizon}"]).sort_values("origin_date").copy()
        valid["rule_sign"] = np.sign(valid["signal"])
        valid = valid[valid["rule_sign"] != 0].copy()
        valid["correct"] = valid["rule_sign"] == np.sign(valid[target])
        valid["signed_return"] = valid["rule_sign"] * valid[target]
        valid["signed_rupee"] = valid["rule_sign"] * (
            np.expm1(valid[target]) * panel.loc[valid["origin_index"], "8ANI"].to_numpy(float)
        )
        block = gf.block_for(valid, horizon)
        accuracy, accuracy_low, accuracy_high = ci(valid["correct"].astype(float).to_numpy(), block)
        signed, signed_low, signed_high = ci(valid["signed_return"].to_numpy(float), block)

        # Expanding walk-forward comparison to the majority class, with no tuning.
        wf_rows = []
        for i in range(12, len(valid)):
            history = valid.iloc[:i]
            row = valid.iloc[i]
            majority_up = float((history[target] > 0).mean()) >= .5
            majority_sign = 1 if majority_up else -1
            wf_rows.append({
                "horizon": horizon, "origin_date": row["origin_date"],
                "signal": row["signal"], "rule_sign": int(row["rule_sign"]),
                "actual_return": row[target], "rule_correct": bool(row["correct"]),
                "majority_sign": majority_sign,
                "majority_correct": majority_sign == np.sign(row[target]),
                "signed_return": row["signed_return"], "signed_rupee": row["signed_rupee"],
            })
        wf = pd.DataFrame(wf_rows)
        if len(wf):
            edge, edge_low, edge_high = ci(
                wf["rule_correct"].astype(float).to_numpy() - wf["majority_correct"].astype(float).to_numpy(),
                max(2, gf.block_for(wf, horizon)),
            )
        else:
            edge = edge_low = edge_high = np.nan
        all_rows.extend(wf_rows)
        summaries.append({
            "horizon": horizon, "native_called_n": len(valid),
            "effective_nonoverlap_n": gf.effective_n(valid, horizon),
            "accuracy": accuracy, "accuracy_ci_low": accuracy_low, "accuracy_ci_high": accuracy_high,
            "mean_signed_log_return": signed, "signed_return_ci_low": signed_low,
            "signed_return_ci_high": signed_high, "mean_signed_rupee": valid["signed_rupee"].mean(),
            "walk_forward_eval_n": len(wf), "walk_forward_accuracy": wf["rule_correct"].mean() if len(wf) else np.nan,
            "walk_forward_majority_accuracy": wf["majority_correct"].mean() if len(wf) else np.nan,
            "walk_forward_accuracy_edge": edge, "edge_ci_low": edge_low, "edge_ci_high": edge_high,
        })
    pd.DataFrame(all_rows).to_csv(OUT / "hrc_sign_rule_walkforward.csv", index=False)
    pd.DataFrame(summaries).to_csv(OUT / "hrc_sign_rule_summary.csv", index=False)


if __name__ == "__main__":
    main()
