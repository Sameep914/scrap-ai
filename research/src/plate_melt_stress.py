from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(r"C:\Users\demos\OneDrive\Documents\ChatGPT\Scrap AI\research")
INPUT = ROOT / "inputs" / "mandi_master.csv"
OUTPUT = ROOT / "outputs" / "plate_melt_stress"
OUTPUT.mkdir(parents=True, exist_ok=True)

HORIZONS = (5, 10, 15, 30, 45, 60, 90)
LOOKBACKS = (40, 60, 90)
THRESHOLDS = (0.75, 1.0, 1.25)
LIVE_PRICE = 38_500.0
SEED = 20260812


def load_panel() -> pd.DataFrame:
    p = pd.read_csv(INPUT)
    p["date"] = pd.to_datetime(p["Date"], errors="coerce")
    price_cols = ["14ANI", "12ANI", "10ANI", "8ANI", "6ANI", "1kgr", "Att", "Melt"]
    for col in price_cols:
        p[col] = pd.to_numeric(p[col], errors="coerce")
    p = p.loc[p["date"].notna()].sort_values("date").drop_duplicates("date").reset_index(drop=True)
    p["gap_days"] = p["date"].diff().dt.days
    # Match the existing live feature: long archive breaks reset the rolling history.
    # The stricter >7-day rule is applied separately to target paths below.
    p["segment"] = p["gap_days"].gt(14).cumsum()
    for col in ["1kgr", "Att", "Melt"]:
        last_date = p["date"].where(p[col].notna()).ffill()
        age = (p["date"] - last_date).dt.days
        p[f"{col}_known"] = p[col].ffill().where(age.le(7))
    p["plate_avg"] = p[["14ANI", "12ANI", "10ANI", "8ANI", "6ANI"]].mean(axis=1)
    p["melt_avg"] = p[["1kgr_known", "Att_known", "Melt_known"]].mean(axis=1)
    p["plate_melt"] = p["plate_avg"] - p["melt_avg"]

    # Current observation is standardized only with the preceding L observations.
    for lookback in LOOKBACKS:
        def z_one(g: pd.DataFrame) -> pd.Series:
            prior = g["plate_melt"].shift(1)
            minimum = math.ceil(0.75 * lookback)
            mean = prior.rolling(lookback, min_periods=minimum).mean()
            std = prior.rolling(lookback, min_periods=minimum).std(ddof=1).replace(0, np.nan)
            return (g["plate_melt"] - mean) / std

        p[f"z{lookback}"] = p.groupby("segment", group_keys=False).apply(
            z_one, include_groups=False
        ).sort_index()

    dates = p["date"].to_numpy(dtype="datetime64[ns]")
    prices = p["8ANI"].to_numpy(float)
    bad_gap = p["gap_days"].gt(7).to_numpy(int)
    cumulative_bad = np.cumsum(bad_gap)
    for horizon in HORIZONS:
        endpoint = np.searchsorted(dates, dates + np.timedelta64(horizon, "D"), side="left")
        end_date = np.full(len(p), np.datetime64("NaT"), dtype="datetime64[ns]")
        end_price = np.full(len(p), np.nan)
        end_index = np.full(len(p), -1, dtype=int)
        rows = np.flatnonzero(endpoint < len(p))
        end_date[rows] = dates[endpoint[rows]]
        end_price[rows] = prices[endpoint[rows]]
        end_index[rows] = endpoint[rows]
        elapsed = (end_date - dates) / np.timedelta64(1, "D")
        tolerance_ok = (elapsed >= horizon) & (elapsed <= horizon + 4)
        crossing = np.ones(len(p), dtype=bool)
        valid_endpoint = end_index.ge(0) if isinstance(end_index, pd.Series) else end_index >= 0
        origin = np.flatnonzero(valid_endpoint)
        crossing[origin] = (cumulative_bad[end_index[origin]] - cumulative_bad[origin]) > 0
        valid = tolerance_ok & ~crossing & np.isfinite(prices) & np.isfinite(end_price)
        p[f"end_index_{horizon}"] = np.where(valid, end_index, -1)
        p[f"end_{horizon}"] = pd.to_datetime(end_date).where(valid)
        p[f"ret_{horizon}"] = np.where(valid, np.log(end_price / prices), np.nan)
        p[f"down_{horizon}"] = np.where(valid, end_price < prices, np.nan)
    return p


def greedy_indices(panel: pd.DataFrame, called_indices: np.ndarray, horizon: int) -> np.ndarray:
    chosen: list[int] = []
    next_date = pd.Timestamp.min
    for idx in called_indices:
        if panel.at[idx, "date"] >= next_date:
            chosen.append(int(idx))
            next_date = panel.at[idx, f"end_{horizon}"]
    return np.asarray(chosen, dtype=int)


def phase_cohorts(panel: pd.DataFrame, called_indices: np.ndarray, horizon: int) -> list[np.ndarray]:
    if not len(called_indices):
        return []
    first_end = panel.at[int(called_indices[0]), f"end_{horizon}"]
    starts = [i for i, idx in enumerate(called_indices) if panel.at[int(idx), "date"] < first_end]
    cohorts: list[np.ndarray] = []
    seen: set[tuple[int, ...]] = set()
    for start in starts:
        cohort = greedy_indices(panel, called_indices[start:], horizon)
        key = tuple(cohort.tolist())
        if key and key not in seen:
            seen.add(key)
            cohorts.append(cohort)
    return cohorts


def metrics(panel: pd.DataFrame, indices: np.ndarray, horizon: int) -> dict[str, float | int]:
    if not len(indices):
        return {"n": 0, "hits": 0, "hit_rate": np.nan, "binom_p": np.nan,
                "mean_signed": np.nan, "median_signed": np.nan}
    ret = -panel.loc[indices, f"ret_{horizon}"].to_numpy(float)
    hits = panel.loc[indices, f"down_{horizon}"].to_numpy(float).astype(bool)
    hit_n = int(hits.sum())
    binom_p = sum(math.comb(len(indices), k) for k in range(hit_n, len(indices) + 1)) / (2 ** len(indices))
    return {
        "n": int(len(indices)),
        "hits": hit_n,
        "hit_rate": float(hits.mean()),
        "binom_p": float(binom_p),
        "mean_signed": float(np.mean(ret)),
        "median_signed": float(np.median(ret)),
    }


def moving_block_ci(values: np.ndarray, block: int, rng: np.random.Generator,
                    reps: int = 4000) -> tuple[float, float]:
    values = values[np.isfinite(values)]
    n = len(values)
    if n < 5:
        return np.nan, np.nan
    block = max(1, min(int(block), n))
    starts = rng.integers(0, n, size=(reps, math.ceil(n / block)))
    offsets = np.arange(block)
    samples = (starts[:, :, None] + offsets[None, None, :]) % n
    samples = samples.reshape(reps, -1)[:, :n]
    means = values[samples].mean(axis=1)
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def period_metrics(panel: pd.DataFrame, called: np.ndarray, horizon: int,
                   start: pd.Timestamp, stop: pd.Timestamp) -> dict[str, float | int]:
    period = np.asarray([
        idx for idx in called if start <= panel.at[int(idx), "date"] < stop
    ], dtype=int)
    return metrics(panel, greedy_indices(panel, period, horizon), horizon)


def evaluate_candidate(panel: pd.DataFrame, lookback: int, threshold: float,
                       horizon: int, rng: np.random.Generator) -> tuple[dict, np.ndarray]:
    z = panel[f"z{lookback}"]
    signal = z.gt(threshold)
    eligible = panel[f"ret_{horizon}"].notna() & z.notna()
    called = np.flatnonzero((eligible & signal).to_numpy())
    # Entry is defined on the complete causal signal path, then restricted to label-safe origins.
    prior_signal = signal.shift(1, fill_value=False)
    prior_segment = panel["segment"].shift(1)
    entry = signal & (~prior_signal | panel["segment"].ne(prior_segment))
    entries = np.flatnonzero((eligible & entry).to_numpy())
    greedy = greedy_indices(panel, called, horizon)
    all_m = metrics(panel, called, horizon)
    episode_m = metrics(panel, entries, horizon)
    greedy_m = metrics(panel, greedy, horizon)

    if len(called) > 1:
        spacing = np.median(np.diff(panel.loc[called, "date"].to_numpy()) / np.timedelta64(1, "D"))
    else:
        spacing = 1.0
    block = max(1, int(math.ceil(horizon / max(float(spacing), 1.0))))
    mbb_low, mbb_high = moving_block_ci(
        -panel.loc[called, f"ret_{horizon}"].to_numpy(float), block, rng
    )
    phases = phase_cohorts(panel, called, horizon)
    phase_m = [metrics(panel, cohort, horizon) for cohort in phases]

    valid_dates = panel.loc[panel[f"ret_{horizon}"].notna(), "date"]
    lo, hi = valid_dates.min(), valid_dates.max() + pd.Timedelta(days=1)
    half_edges = pd.date_range(lo, hi, periods=3)
    third_edges = pd.date_range(lo, hi, periods=4)
    halves = [period_metrics(panel, called, horizon, half_edges[i], half_edges[i + 1]) for i in range(2)]
    thirds = [period_metrics(panel, called, horizon, third_edges[i], third_edges[i + 1]) for i in range(3)]
    post = period_metrics(panel, called, horizon, pd.Timestamp("2024-09-18"), pd.Timestamp.max)

    record: dict[str, float | int | bool] = {
        "lookback": lookback,
        "threshold": threshold,
        "horizon": horizon,
        "called_n": all_m["n"],
        "called_hit": all_m["hit_rate"],
        "called_mean_signed": all_m["mean_signed"],
        "episode_n": episode_m["n"],
        "episode_hit": episode_m["hit_rate"],
        "episode_binom_p": episode_m["binom_p"],
        "episode_mean_signed": episode_m["mean_signed"],
        "greedy_n": greedy_m["n"],
        "greedy_hits": greedy_m["hits"],
        "greedy_hit": greedy_m["hit_rate"],
        "greedy_binom_p": greedy_m["binom_p"],
        "greedy_mean_signed": greedy_m["mean_signed"],
        "greedy_median_signed": greedy_m["median_signed"],
        "mbb_block": block,
        "mbb_ci_low": mbb_low,
        "mbb_ci_high": mbb_high,
        "phase_count": len(phase_m),
        "phase_n_min": min((m["n"] for m in phase_m), default=0),
        "phase_n_median": float(np.median([m["n"] for m in phase_m])) if phase_m else 0,
        "phase_hit_min": min((m["hit_rate"] for m in phase_m), default=np.nan),
        "phase_hit_median": float(np.median([m["hit_rate"] for m in phase_m])) if phase_m else np.nan,
        "phase_mean_min": min((m["mean_signed"] for m in phase_m), default=np.nan),
        "phase_mean_median": float(np.median([m["mean_signed"] for m in phase_m])) if phase_m else np.nan,
        "post_n": post["n"],
        "post_hit": post["hit_rate"],
        "post_mean_signed": post["mean_signed"],
    }
    for i, m in enumerate(halves, 1):
        record[f"half{i}_n"] = m["n"]
        record[f"half{i}_hit"] = m["hit_rate"]
        record[f"half{i}_mean_signed"] = m["mean_signed"]
    for i, m in enumerate(thirds, 1):
        record[f"third{i}_n"] = m["n"]
        record[f"third{i}_hit"] = m["hit_rate"]
        record[f"third{i}_mean_signed"] = m["mean_signed"]
    return record, called


def holm_adjust(pvalues: np.ndarray) -> np.ndarray:
    result = np.full(len(pvalues), np.nan)
    finite = np.flatnonzero(np.isfinite(pvalues))
    if not len(finite):
        return result
    order = finite[np.argsort(pvalues[finite])]
    m = len(order)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * pvalues[idx])
        result[idx] = min(1.0, running)
    return result


def max_shift_adjustment(panel: pd.DataFrame, results: pd.DataFrame,
                         reps: int = 3000) -> tuple[np.ndarray, dict]:
    n = len(panel)
    rng = np.random.default_rng(SEED + 99)
    allowed = np.arange(91, n - 91)
    if not len(allowed):
        allowed = np.arange(1, n)
    configs = [(int(r.lookback), float(r.threshold), int(r.horizon)) for r in results.itertuples()]
    signals = {
        (l, t): panel[f"z{l}"].gt(t).to_numpy()
        for l in LOOKBACKS for t in THRESHOLDS
    }
    returns = {h: panel[f"ret_{h}"].to_numpy(float) for h in HORIZONS}

    def t_stat(indices: np.ndarray, horizon: int) -> float:
        if len(indices) < 5:
            return -np.inf
        x = -returns[horizon][indices]
        sd = np.std(x, ddof=1)
        return float(np.mean(x) / (sd / math.sqrt(len(x)))) if sd > 0 else -np.inf

    observed = np.full(len(configs), np.nan)
    for j, (_, _, h) in enumerate(configs):
        row = results.iloc[j]
        if row.greedy_n >= 5:
            indices = greedy_indices(
                panel,
                np.flatnonzero(
                    panel[f"ret_{h}"].notna().to_numpy()
                    & signals[(configs[j][0], configs[j][1])]
                ),
                h,
            )
            observed[j] = t_stat(indices, h)

    null_max = np.full(reps, np.nan)
    for rep in range(reps):
        shift = int(rng.choice(allowed))
        best = -np.inf
        shifted_cache = {key: np.roll(value, shift) for key, value in signals.items()}
        for l, t, h in configs:
            called = np.flatnonzero(np.isfinite(returns[h]) & shifted_cache[(l, t)])
            selected = greedy_indices(panel, called, h)
            best = max(best, t_stat(selected, h))
        null_max[rep] = best
    adjusted = np.asarray([
        (1 + np.sum(null_max >= value)) / (reps + 1) if np.isfinite(value) else np.nan
        for value in observed
    ])
    metadata = {
        "reps": reps,
        "candidate_count": len(configs),
        "null_max_95": float(np.quantile(null_max, 0.95)),
        "observed_max_t": float(np.nanmax(observed)),
        "family_p": float((1 + np.sum(null_max >= np.nanmax(observed))) / (reps + 1)),
    }
    return adjusted, metadata


def live_analogs(panel: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    today = panel.iloc[-1]
    current_price = float(today["8ANI"])
    base = results[(results.lookback == 60) & np.isclose(results.threshold, 1.0)].set_index("horizon")
    signal = panel["z60"].gt(1.0)
    for horizon in HORIZONS:
        valid = signal & panel[f"ret_{horizon}"].notna()
        idx = np.flatnonzero(valid.to_numpy())
        signed = -panel.loc[idx, f"ret_{horizon}"].to_numpy(float)
        row = base.loc[horizon]
        # Strict standard: independent support, familywise test, dependence CI, and stability.
        stable_parts = [row[f"half{i}_mean_signed"] > 0 for i in (1, 2)] + [
            row[f"third{i}_mean_signed"] > 0 for i in (1, 2, 3)
        ]
        defensible = bool(
            row.greedy_n >= 20
            and row.max_shift_p <= 0.05
            and row.greedy_holm_p <= 0.05
            and row.mbb_ci_low > 0
            and row.phase_mean_min > 0
            and row.post_mean_signed > 0
            and all(stable_parts)
        )
        mean_signed = float(np.mean(signed)) if len(signed) else np.nan
        median_signed = float(np.median(signed)) if len(signed) else np.nan
        q10, q90 = np.quantile(signed, [0.10, 0.90]) if len(signed) else (np.nan, np.nan)
        rows.append({
            "as_of": today["date"].date().isoformat(),
            "spot_8ANI": current_price,
            "live_z60": float(today["z60"]),
            "signal": "DOWN" if today["z60"] > 1 else "OFF",
            "horizon": horizon,
            "analog_rows": len(signed),
            "independent_n": int(row.greedy_n),
            "defensible": defensible,
            "mean_future_return": -mean_signed,
            "median_future_return": -median_signed,
            "return_80_low": -q90,
            "return_80_high": -q10,
            "mean_implied_price": current_price * math.exp(-mean_signed) if defensible else np.nan,
            "median_implied_price": current_price * math.exp(-median_signed) if defensible else np.nan,
            "price_80_low": current_price * math.exp(-q90) if defensible else np.nan,
            "price_80_high": current_price * math.exp(-q10) if defensible else np.nan,
        })
    return pd.DataFrame(rows)


def main() -> None:
    panel = load_panel()
    rng = np.random.default_rng(SEED)
    records: list[dict] = []
    for lookback in LOOKBACKS:
        for threshold in THRESHOLDS:
            for horizon in HORIZONS:
                record, _ = evaluate_candidate(panel, lookback, threshold, horizon, rng)
                records.append(record)
    results = pd.DataFrame(records)
    results["greedy_holm_p"] = holm_adjust(results["greedy_binom_p"].to_numpy(float))
    results["episode_holm_p"] = holm_adjust(results["episode_binom_p"].to_numpy(float))
    results["max_shift_p"], shift_meta = max_shift_adjustment(panel, results)
    live = live_analogs(panel, results)
    results.to_csv(OUTPUT / "robustness_63.csv", index=False)
    results[(results.lookback == 60) & np.isclose(results.threshold, 1.0)].to_csv(
        OUTPUT / "base_positive_side.csv", index=False
    )
    live.to_csv(OUTPUT / "live_positive_side.csv", index=False)
    metadata = {
        "data_start": panel.date.min().date().isoformat(),
        "data_end": panel.date.max().date().isoformat(),
        "rows": len(panel),
        "gap_rule_days": 7,
        "excluded_gap_starts": panel.loc[panel.gap_days.gt(7), "date"].dt.date.astype(str).tolist(),
        "target_tolerance_days": 4,
        "signal_side": "positive z only => DOWN",
        "live": {"z40": float(panel.iloc[-1].z40), "z60": float(panel.iloc[-1].z60),
                 "z90": float(panel.iloc[-1].z90), "price": float(panel.iloc[-1]["8ANI"])},
        "multiplicity": shift_meta,
    }
    (OUTPUT / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(results[(results.lookback == 60) & np.isclose(results.threshold, 1.0)][[
        "horizon", "called_n", "episode_n", "episode_hit", "episode_binom_p",
        "greedy_n", "greedy_hit", "greedy_binom_p", "greedy_holm_p",
        "greedy_mean_signed", "mbb_ci_low", "mbb_ci_high", "phase_mean_min",
        "post_mean_signed", "max_shift_p",
    ]].to_string(index=False))
    print("\nLIVE\n", live.to_string(index=False))
    print("\nMULTIPLICITY\n", json.dumps(shift_meta, indent=2))


if __name__ == "__main__":
    main()
