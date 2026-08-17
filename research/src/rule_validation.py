from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(r"C:\Users\demos\OneDrive\Documents\ChatGPT\Scrap AI\research")
INPUTS = ROOT / "inputs"
OUTPUTS = ROOT / "outputs"
OUTPUTS.mkdir(parents=True, exist_ok=True)

HORIZONS = [5, 10, 15, 30, 45, 60, 90]
RNG = np.random.default_rng(20260812)


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype(float)


def segmented_rolling_z(data: pd.DataFrame, value: str, window: int, minimum: int) -> pd.Series:
    def one(segment: pd.DataFrame) -> pd.Series:
        x = segment[value]
        past = x.shift(1)
        mean = past.rolling(window, min_periods=minimum).mean()
        std = past.rolling(window, min_periods=minimum).std(ddof=1).replace(0, np.nan)
        return (x - mean) / std

    return data.groupby("segment", group_keys=False).apply(one, include_groups=False).sort_index()


def load_mandi() -> pd.DataFrame:
    data = pd.read_csv(INPUTS / "mandi_master.csv")
    data["date"] = pd.to_datetime(data["Date"], errors="coerce")
    prices = ["14ANI", "12ANI", "10ANI", "8ANI", "6ANI", "4ANI", "5kg", "2kg", "1kgr", "Att", "Melt"]
    for col in prices:
        data[col] = numeric(data[col])
    data = data[data["date"].notna()].sort_values("date").drop_duplicates("date").reset_index(drop=True)
    data["gap_days"] = data["date"].diff().dt.days
    data["segment"] = data["gap_days"].gt(14).cumsum()

    # Only short, explicitly aged carries for the three melting grades.
    for col in ["1kgr", "Att", "Melt"]:
        observed = data["date"].where(data[col].notna()).ffill()
        age = (data["date"] - observed).dt.days
        data[f"{col}_known"] = data[col].ffill().where(age.le(7))
    data["plate_avg"] = data[["14ANI", "12ANI", "10ANI", "8ANI", "6ANI"]].mean(axis=1)
    data["melt_avg"] = data[["1kgr_known", "Att_known", "Melt_known"]].mean(axis=1)
    data["plate_melt"] = data["plate_avg"] - data["melt_avg"]
    data["eight_melt"] = data["8ANI"] - data["Melt_known"]
    data["ten_melt"] = data["10ANI"] - data["Melt_known"]
    data["plate_melt_z60"] = segmented_rolling_z(data, "plate_melt", 60, 45)
    data["eight_melt_z60"] = segmented_rolling_z(data, "eight_melt", 60, 45)
    data["ten_melt_z60"] = segmented_rolling_z(data, "ten_melt", 60, 45)
    return data


def load_bhavnagar() -> pd.DataFrame:
    data = pd.read_csv(INPUTS / "bhavnagar_Bhavnagar_Prices.csv", skiprows=4)
    data = data.iloc[:, :4].copy()
    data.columns = ["serial", "tmt", "ingot", "billet"]
    data["date"] = pd.Timestamp("1899-12-30") + pd.to_timedelta(numeric(data["serial"]), unit="D")
    for col in ["tmt", "ingot", "billet"]:
        data[col] = numeric(data[col])
    data = data[data["date"].notna()].sort_values("date").reset_index(drop=True)

    # Momentum is computed on each market's own reported observations, never on calendar-filled values.
    frames: list[pd.DataFrame] = []
    for col in ["tmt", "ingot", "billet"]:
        obs = data.loc[data[col].notna(), ["date", col]].copy()
        obs[f"{col}_mom10"] = np.log(obs[col] / obs[col].shift(10))
        obs[f"{col}_mom20"] = np.log(obs[col] / obs[col].shift(20))
        frames.append(obs)
    out = frames[0]
    for frame in frames[1:]:
        out = out.merge(frame, on="date", how="outer")
    return out.sort_values("date").reset_index(drop=True)


def load_turkey_nearby() -> pd.DataFrame:
    data = pd.read_csv(INPUTS / "turkey_scrap_daily_nearby.csv")
    data["date"] = pd.to_datetime(data["Time"], errors="coerce")
    for col in ["Open", "High", "Low", "Latest", "Change", "Volume", "Open Int"]:
        data[col] = numeric(data[col])
    data = data[data["date"].notna()].sort_values("date").drop_duplicates("date").reset_index(drop=True)
    data["roll"] = data["Symbol"].ne(data["Symbol"].shift(1))
    raw = np.log(data["Latest"] / data["Latest"].shift(1))
    # Barchart Change equals the cross-symbol gap on every observed roll; it is not a
    # same-contract return. The incoming/outgoing basis is therefore unidentified.
    # Missing roll returns are preserved rather than silently back-adjusted.
    data["clean_return"] = raw.where(~data["roll"])
    data.loc[data.index[0], "clean_return"] = np.nan
    data["clean_log_index"] = data["clean_return"].fillna(0).cumsum()
    for lag in [5, 10, 20, 30, 60]:
        # A partial non-roll momentum excludes at most one unidentified roll gap.
        # The accompanying flag lets models/rules distinguish fully observed windows.
        data[f"turkey_rolls{lag}"] = data["roll"].rolling(lag, min_periods=lag).sum()
        data[f"turkey_mom{lag}"] = data["clean_return"].rolling(lag, min_periods=max(2, lag - 1)).sum()
        data.loc[data[f"turkey_rolls{lag}"].gt(1), f"turkey_mom{lag}"] = np.nan
    data["turkey_rv20"] = data["clean_return"].shift(1).rolling(20, min_periods=15).std(ddof=1)
    data["turkey_volume_share20"] = data["Volume"].gt(0).shift(1).rolling(20, min_periods=15).mean()
    data["turkey_oi_median20"] = data["Open Int"].shift(3).rolling(20, min_periods=15).median()
    data["turkey_zero_volume"] = data["Volume"].eq(0).astype(float)
    return data


def strict_asof(left: pd.DataFrame, right: pd.DataFrame, prefix: str) -> pd.DataFrame:
    right = right.rename(columns={"date": f"{prefix}_date"}).sort_values(f"{prefix}_date")
    out = pd.merge_asof(
        left.sort_values("date"),
        right,
        left_on="date",
        right_on=f"{prefix}_date",
        direction="backward",
        allow_exact_matches=False,
    )
    out[f"{prefix}_age"] = (out["date"] - out[f"{prefix}_date"]).dt.days
    return out


def add_features() -> pd.DataFrame:
    panel = strict_asof(load_mandi(), load_bhavnagar(), "bhav")
    local_cols = [c for c in panel.columns if c.startswith(("tmt", "ingot", "billet"))]
    panel.loc[panel["bhav_age"].gt(7), local_cols] = np.nan
    panel["log_scrap_ingot"] = np.log(panel["8ANI"] / panel["ingot"])
    panel["scrap_ingot_z60"] = segmented_rolling_z(panel, "log_scrap_ingot", 60, 45)

    turkey_cols = [
        "date", "Symbol", "Latest", "Volume", "Open Int", "roll", "clean_return", "clean_log_index",
        "turkey_mom5", "turkey_mom10", "turkey_mom20", "turkey_mom30", "turkey_mom60",
        "turkey_rolls5", "turkey_rolls10", "turkey_rolls20", "turkey_rolls30", "turkey_rolls60",
        "turkey_rv20", "turkey_volume_share20", "turkey_oi_median20", "turkey_zero_volume",
    ]
    panel = strict_asof(panel, load_turkey_nearby()[turkey_cols], "turkey")
    stale = panel["turkey_age"].gt(4)
    stale_cols = [c for c in turkey_cols if c not in {"date", "Symbol", "roll"}]
    panel.loc[stale, stale_cols] = np.nan
    panel.loc[stale, "Symbol"] = None
    panel.loc[stale, "roll"] = False

    # Five rules fixed before looking at outcomes. Flat/disagreement states deliberately produce no call.
    panel["rule_plate_melt"] = np.where(
        panel["plate_melt_z60"].gt(1), -1, np.where(panel["plate_melt_z60"].lt(-1), 1, 0)
    )
    panel["rule_eight_melt"] = np.where(
        panel["eight_melt_z60"].gt(1), -1, np.where(panel["eight_melt_z60"].lt(-1), 1, 0)
    )
    panel["rule_ten_melt"] = np.where(
        panel["ten_melt_z60"].gt(1), -1, np.where(panel["ten_melt_z60"].lt(-1), 1, 0)
    )
    panel["rule_scrap_ingot"] = np.where(
        panel["scrap_ingot_z60"].gt(1), -1, np.where(panel["scrap_ingot_z60"].lt(-1), 1, 0)
    )
    local_up = panel["ingot_mom10"].gt(0) & panel["tmt_mom10"].gt(0)
    local_down = panel["ingot_mom10"].lt(0) & panel["tmt_mom10"].lt(0)
    panel["rule_local_momentum"] = np.where(local_up, 1, np.where(local_down, -1, 0))
    value_up = panel["scrap_ingot_z60"].lt(-1) & local_up
    value_down = panel["scrap_ingot_z60"].gt(1) & local_down
    panel["rule_value_momentum"] = np.where(value_up, 1, np.where(value_down, -1, 0))
    panel["rule_turkey_momentum"] = np.where(
        panel["turkey_mom20"].notna(), np.sign(panel["turkey_mom20"]), 0
    ).astype(int)
    return panel


def add_targets(panel: pd.DataFrame) -> pd.DataFrame:
    dates = panel["date"].to_numpy(dtype="datetime64[ns]")
    prices = panel["8ANI"].to_numpy(float)
    for horizon in HORIZONS:
        endpoint = np.searchsorted(dates, dates + np.timedelta64(horizon, "D"), side="left")
        end_date = np.full(len(panel), np.datetime64("NaT"), dtype="datetime64[ns]")
        end_price = np.full(len(panel), np.nan)
        valid_row = np.flatnonzero(endpoint < len(panel))
        end_date[valid_row] = dates[endpoint[valid_row]]
        end_price[valid_row] = prices[endpoint[valid_row]]
        elapsed = (end_date - dates) / np.timedelta64(1, "D")
        valid = (elapsed >= horizon) & (elapsed <= horizon + 4)
        panel[f"end_{horizon}"] = pd.to_datetime(end_date).where(valid)
        panel[f"ret_{horizon}"] = np.where(valid, np.log(end_price / prices), np.nan)
        panel[f"change_{horizon}"] = np.where(valid, end_price - prices, np.nan)
        panel[f"direction_{horizon}"] = np.where(
            valid, np.where(end_price > prices, 1, np.where(end_price < prices, -1, 0)), np.nan
        )
    return panel


def phase_cohorts(frame: pd.DataFrame) -> list[pd.DataFrame]:
    frame = frame.sort_values("date")
    if frame.empty:
        return []
    first_date = frame["date"].iloc[0]
    first_end = frame["end"].iloc[0]
    possible = frame.index[frame["date"] < first_end].tolist()
    cohorts: list[pd.DataFrame] = []
    seen: set[tuple[int, ...]] = set()
    for start_idx in possible:
        selected: list[int] = []
        next_date = frame.loc[start_idx, "date"]
        for idx, row in frame.loc[start_idx:].iterrows():
            if row["date"] >= next_date:
                selected.append(idx)
                next_date = row["end"]
        key = tuple(selected)
        if key and key not in seen:
            seen.add(key)
            cohorts.append(frame.loc[selected].copy())
    return cohorts


def moving_block_ci(values: np.ndarray, block: int, reps: int = 2000) -> tuple[float, float, float]:
    values = values[np.isfinite(values)]
    n = len(values)
    if n < 5:
        return np.nan, np.nan, np.nan
    means = np.empty(reps)
    block = max(1, min(block, n))
    for rep in range(reps):
        sample: list[float] = []
        while len(sample) < n:
            start = int(RNG.integers(0, n))
            sample.extend(values[(start + np.arange(block)) % n].tolist())
        means[rep] = float(np.mean(sample[:n]))
    p_one_sided = float((1 + np.sum(means <= 0)) / (reps + 1))
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975)), p_one_sided


def evaluate_rule(panel: pd.DataFrame, rule: str, horizon: int) -> tuple[dict, pd.DataFrame]:
    required = ["date", rule, f"end_{horizon}", f"ret_{horizon}", f"change_{horizon}", f"direction_{horizon}"]
    all_eligible = panel.dropna(subset=[f"ret_{horizon}", rule]).copy()
    called = all_eligible[all_eligible[rule].ne(0)][required].copy()
    called.columns = ["date", "call", "end", "actual_ret", "actual_change", "actual_direction"]
    called["signed_ret"] = called["call"] * called["actual_ret"]
    called["signed_change"] = called["call"] * called["actual_change"]
    called["hit"] = called["call"].eq(called["actual_direction"]).astype(float)
    called["holding_hurdle_inr"] = 30.0 * horizon
    called["net_hold_change_inr"] = called["actual_change"] - called["holding_hurdle_inr"]
    called["economic_target"] = np.sign(called["net_hold_change_inr"])
    called["economic_hit"] = called["call"].eq(called["economic_target"]).astype(float)
    called["signed_net_value_inr"] = called["call"] * called["net_hold_change_inr"]
    cohorts = phase_cohorts(called)
    cohort_means = [float(c["signed_ret"].mean()) for c in cohorts]
    cohort_hits = [float(c["hit"].mean()) for c in cohorts]
    cohort_ns = [len(c) for c in cohorts]
    typical_spacing = max(1, int(round(horizon / max(panel["date"].diff().dt.days.median(), 1))))
    ci_low, ci_high, raw_p = moving_block_ci(called["signed_ret"].to_numpy(float), typical_spacing)
    summary = {
        "rule": rule,
        "horizon": horizon,
        "eligible_n": int(len(all_eligible)),
        "called_n": int(len(called)),
        "coverage": float(len(called) / len(all_eligible)) if len(all_eligible) else np.nan,
        "up_calls": int(called["call"].eq(1).sum()),
        "down_calls": int(called["call"].eq(-1).sum()),
        "flat_outcomes": int(called["actual_direction"].eq(0).sum()),
        "raw_hit_rate_including_flat": float(called["hit"].mean()) if len(called) else np.nan,
        "mean_signed_log_return": float(called["signed_ret"].mean()) if len(called) else np.nan,
        "median_signed_change_inr": float(called["signed_change"].median()) if len(called) else np.nan,
        "holding_hurdle_inr": 30 * horizon,
        "economic_hit_rate": float(called["economic_hit"].mean()) if len(called) else np.nan,
        "mean_signed_net_value_inr": float(called["signed_net_value_inr"].mean()) if len(called) else np.nan,
        "median_signed_net_value_inr": float(called["signed_net_value_inr"].median()) if len(called) else np.nan,
        "bootstrap_mean_signed_ci_low": ci_low,
        "bootstrap_mean_signed_ci_high": ci_high,
        "raw_one_sided_p": raw_p,
        "phase_cohort_count": len(cohorts),
        "nonoverlap_n_min": int(min(cohort_ns)) if cohort_ns else 0,
        "nonoverlap_n_median": float(np.median(cohort_ns)) if cohort_ns else 0,
        "nonoverlap_n_max": int(max(cohort_ns)) if cohort_ns else 0,
        "phase_mean_signed_min": min(cohort_means) if cohort_means else np.nan,
        "phase_mean_signed_median": float(np.median(cohort_means)) if cohort_means else np.nan,
        "phase_hit_min": min(cohort_hits) if cohort_hits else np.nan,
        "phase_hit_median": float(np.median(cohort_hits)) if cohort_hits else np.nan,
    }
    return summary, called


def max_null_adjustment(panel: pd.DataFrame, rules: list[str], summaries: pd.DataFrame, reps: int = 1500) -> dict:
    observed_stats: list[float] = []
    for row in summaries.itertuples(index=False):
        if row.nonoverlap_n_median < 3 or not np.isfinite(row.mean_signed_log_return):
            observed_stats.append(np.nan)
            continue
        scale = panel[f"ret_{row.horizon}"].std(ddof=1)
        if scale and np.isfinite(scale):
            observed_stats.append(row.mean_signed_log_return * math.sqrt(row.nonoverlap_n_median) / scale)
        else:
            observed_stats.append(np.nan)
    summaries["standardized_edge"] = observed_stats
    finite_observed = np.asarray(observed_stats, dtype=float)
    finite_observed = finite_observed[np.isfinite(finite_observed)]
    observed_max = float(np.max(finite_observed)) if len(finite_observed) else np.nan

    n = len(panel)
    min_shift = min(70, max(10, n // 5))
    allowed = np.arange(min_shift, n - min_shift)
    null_max = np.full(reps, np.nan)
    rule_values = {rule: panel[rule].to_numpy(float) for rule in rules}
    for rep in range(reps):
        shift = int(RNG.choice(allowed))
        best = -np.inf
        for rule in rules:
            shifted = np.roll(rule_values[rule], shift)
            for horizon in HORIZONS:
                y = panel[f"ret_{horizon}"].to_numpy(float)
                valid = np.isfinite(y) & np.isfinite(shifted) & (shifted != 0)
                matching = summaries[(summaries["rule"] == rule) & (summaries["horizon"] == horizon)]
                if valid.sum() < 5 or matching.empty:
                    continue
                neff = float(matching.iloc[0]["nonoverlap_n_median"])
                if neff < 3:
                    continue
                scale = float(np.nanstd(y[valid], ddof=1))
                if not scale:
                    continue
                stat = float(np.mean(shifted[valid] * y[valid]) * math.sqrt(neff) / scale)
                best = max(best, stat)
        null_max[rep] = best
    null_max = null_max[np.isfinite(null_max)]
    summaries["max_shift_adjusted_p"] = [
        float((1 + np.sum(null_max >= value)) / (1 + len(null_max))) if np.isfinite(value) else np.nan
        for value in summaries["standardized_edge"].to_numpy(float)
    ]
    summaries["passes_prespecified_rule_gate"] = (
        summaries["nonoverlap_n_median"].ge(20)
        & summaries["bootstrap_mean_signed_ci_low"].gt(0)
        & summaries["phase_mean_signed_min"].ge(0)
        & summaries["max_shift_adjusted_p"].le(0.05)
        & summaries["economic_hit_rate"].gt(0.50)
    )
    return {
        "candidate_count": int(len(summaries)),
        "replicates": int(len(null_max)),
        "observed_max_standardized_edge": float(observed_max),
        "expected_best_under_shift_null": float(np.mean(null_max)),
        "null_95": float(np.quantile(null_max, 0.95)),
        "selection_adjusted_p": float((1 + np.sum(null_max >= observed_max)) / (1 + len(null_max))),
        "survives_5pct_familywise_gate": bool(observed_max > np.quantile(null_max, 0.95)),
    }


def main() -> None:
    panel = add_targets(add_features())
    rules = [
        "rule_plate_melt",
        "rule_eight_melt",
        "rule_ten_melt",
        "rule_scrap_ingot",
        "rule_local_momentum",
        "rule_value_momentum",
        "rule_turkey_momentum",
    ]
    summaries: list[dict] = []
    for rule in rules:
        for horizon in HORIZONS:
            summary, calls = evaluate_rule(panel, rule, horizon)
            summaries.append(summary)
            calls.to_csv(OUTPUTS / f"rule_calls_{rule.removeprefix('rule_')}_{horizon}d.csv", index=False)
    summary_frame = pd.DataFrame(summaries)
    adjustment = max_null_adjustment(panel, rules, summary_frame)

    live = panel.iloc[-1]
    live_rows = []
    for rule in rules:
        live_rows.append({
            "as_of": str(live["date"].date()),
            "rule": rule,
            "call_code": int(live[rule]),
            "call": {1: "UP / HOLD", -1: "DOWN / SELL", 0: "NO CALL"}[int(live[rule])],
            "plate_melt_z60": live.get("plate_melt_z60", np.nan),
            "eight_melt_z60": live.get("eight_melt_z60", np.nan),
            "ten_melt_z60": live.get("ten_melt_z60", np.nan),
            "scrap_ingot_z60": live.get("scrap_ingot_z60", np.nan),
            "ingot_mom10": live.get("ingot_mom10", np.nan),
            "tmt_mom10": live.get("tmt_mom10", np.nan),
            "turkey_mom20": live.get("turkey_mom20", np.nan),
            "turkey_age": live.get("turkey_age", np.nan),
        })

    panel.to_csv(OUTPUTS / "rule_feature_panel.csv", index=False)
    summary_frame.to_csv(OUTPUTS / "rule_backtest_summary.csv", index=False)
    pd.DataFrame(live_rows).to_csv(OUTPUTS / "live_rule_signals.csv", index=False)
    metadata = {
        "method": "Pre-specified causal threshold rules; true calendar targets; strict prior-date external joins; moving-block bootstrap; all phase-offset non-overlap cohorts; common circular-shift max-null across 35 rule/horizon candidates.",
        "horizons": HORIZONS,
        "target_tolerance_days": 4,
        "mandi_rows": int(len(panel)),
        "main_continuous_start": "2024-09-18",
        "large_gaps_days": panel.loc[panel["gap_days"].gt(14), "gap_days"].astype(int).tolist(),
        "turkey_roll_count": int(load_turkey_nearby()["roll"].sum() - 1),
        "multiple_testing": adjustment,
    }
    (OUTPUTS / "rule_study_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({"multiple_testing": adjustment, "live": live_rows}, indent=2, default=str))


if __name__ == "__main__":
    main()
