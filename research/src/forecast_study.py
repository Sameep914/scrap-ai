from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(r"C:\Users\demos\OneDrive\Documents\ChatGPT\Scrap AI\research")
INPUTS = ROOT / "inputs"
OUTPUTS = ROOT / "outputs"
OUTPUTS.mkdir(parents=True, exist_ok=True)

HORIZONS = [5, 10, 15, 30, 45, 60, 90]
TARGET_TOLERANCE_DAYS = 4
MAX_FEATURE_STALENESS_DAYS = 4
RNG = np.random.default_rng(20260812)


def as_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype(float)


def rolling_z(series: pd.Series, window: int, min_periods: int | None = None) -> pd.Series:
    min_periods = min_periods or window
    past = series.shift(1)
    mu = past.rolling(window, min_periods=min_periods).mean()
    sigma = past.rolling(window, min_periods=min_periods).std(ddof=1)
    return (series - mu) / sigma.replace(0, np.nan)


def rolling_robust_z(series: pd.Series, window: int, min_periods: int | None = None) -> pd.Series:
    min_periods = min_periods or window
    past = series.shift(1)
    med = past.rolling(window, min_periods=min_periods).median()
    mad = past.rolling(window, min_periods=min_periods).apply(
        lambda x: np.nanmedian(np.abs(x - np.nanmedian(x))), raw=True
    )
    return (series - med) / (1.4826 * mad.replace(0, np.nan))


def ewma_vol(log_returns: pd.Series, lam: float = 0.94) -> pd.Series:
    out = np.full(len(log_returns), np.nan)
    var = np.nan
    for i, value in enumerate(log_returns.to_numpy()):
        if i == 0:
            continue
        prior = log_returns.iloc[i - 1]
        if np.isnan(prior):
            continue
        if np.isnan(var):
            history = log_returns.iloc[max(0, i - 30) : i].dropna().to_numpy()
            var = float(np.var(history, ddof=1)) if len(history) >= 5 else float(prior**2)
        else:
            var = lam * var + (1 - lam) * float(prior**2)
        out[i] = math.sqrt(max(var, 0))
    return pd.Series(out, index=log_returns.index)


def load_mandi() -> pd.DataFrame:
    mandi = pd.read_csv(INPUTS / "mandi_master.csv")
    mandi["date"] = pd.to_datetime(mandi["Date"], errors="coerce")
    numeric_cols = ["14ANI", "12ANI", "10ANI", "8ANI", "6ANI", "4ANI", "5kg", "2kg", "1kgr", "Att", "Melt", "8ANI d/d"]
    for col in numeric_cols:
        mandi[col] = as_float(mandi[col])
    mandi = mandi.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    gaps = mandi["date"].diff().dt.days
    mandi["continuous_segment"] = gaps.gt(14).cumsum()

    # Short, explicitly flagged carry only. The original measurements remain unchanged.
    for col in ["5kg", "1kgr", "Att", "Melt"]:
        observed_date = mandi["date"].where(mandi[col].notna()).ffill()
        mandi[f"{col}_age"] = (mandi["date"] - observed_date).dt.days
        mandi[f"{col}_filled"] = mandi[col].ffill().where(mandi[f"{col}_age"] <= 7)

    plate_cols = ["14ANI", "12ANI", "10ANI", "8ANI", "6ANI"]
    mandi["plate_avg"] = mandi[plate_cols].mean(axis=1)
    mandi["melt_avg"] = mandi[["1kgr_filled", "Att_filled", "Melt_filled"]].mean(axis=1)
    mandi["plate_melt"] = mandi["plate_avg"] - mandi["melt_avg"]
    mandi["eight_melt"] = mandi["8ANI"] - mandi["Melt_filled"]
    mandi["plate_1kgr"] = mandi["plate_avg"] - mandi["1kgr_filled"]
    mandi["ten_melt"] = mandi["10ANI"] - mandi["Melt_filled"]

    log_price = np.log(mandi["8ANI"])
    mandi["ret_1q"] = log_price.diff()
    mandi["ewma_vol"] = ewma_vol(mandi["ret_1q"])
    mandi["unchanged_20"] = mandi["8ANI"].diff().eq(0).shift(1).rolling(20, min_periods=10).mean()
    last_change = mandi["date"].where(mandi["8ANI"].diff().ne(0)).ffill()
    mandi["days_since_change"] = (mandi["date"] - last_change).dt.days
    for lag in [5, 10, 20, 30, 60]:
        mandi[f"own_mom_{lag}"] = np.log(mandi["8ANI"] / mandi["8ANI"].shift(lag))
    for col in ["plate_melt", "eight_melt", "plate_1kgr", "ten_melt"]:
        for window in [60, 120]:
            mandi[f"{col}_z{window}"] = rolling_z(mandi[col], window)
        mandi[f"{col}_rz60"] = rolling_robust_z(mandi[col], 60)
    mandi["monsoon"] = mandi["date"].dt.month.isin([6, 7, 8, 9]).astype(float)
    return mandi


def load_turkey() -> pd.DataFrame:
    turkey = pd.read_csv(INPUTS / "turkey_scrap_C_U26.csv")
    turkey["date"] = pd.to_datetime(turkey["Time"], errors="coerce")
    turkey = turkey[turkey["date"].notna()].copy()
    for col in ["Open", "High", "Low", "Latest", "Change", "Volume", "Open Int"]:
        turkey[col] = as_float(turkey[col])
    turkey = turkey.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    turkey["latest"] = turkey["Latest"]
    turkey["volume"] = turkey["Volume"]
    turkey["open_interest"] = turkey["Open Int"]
    turkey["zero_volume"] = (turkey["volume"] == 0).astype(float)
    turkey["zero_range"] = (turkey["High"] == turkey["Low"]).astype(float)
    turkey["days_to_prompt"] = (pd.Timestamp("2026-09-01") - turkey["date"]).dt.days.astype(float)
    turkey["log_price"] = np.log(turkey["latest"])
    for lag in [5, 10, 20, 30, 60]:
        turkey[f"turkey_mom_{lag}"] = turkey["log_price"].diff(lag)
    turkey["turkey_rv20"] = turkey["log_price"].diff().shift(1).rolling(20, min_periods=10).std(ddof=1)
    turkey["turkey_z60"] = rolling_z(turkey["latest"], 60)
    turkey["volume_share20"] = turkey["volume"].gt(0).shift(1).rolling(20, min_periods=10).mean()
    turkey["oi_median20"] = turkey["open_interest"].shift(3).rolling(20, min_periods=10).median()
    turkey["log_volume"] = np.log1p(turkey["volume"])
    turkey["log_oi_lag3"] = np.log1p(turkey["open_interest"].shift(3))
    return turkey


def asof_turkey(mandi: pd.DataFrame, turkey: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "date", "latest", "volume", "open_interest", "zero_volume", "zero_range",
        "days_to_prompt", "turkey_mom_5", "turkey_mom_10", "turkey_mom_20",
        "turkey_mom_30", "turkey_mom_60", "turkey_rv20", "turkey_z60",
        "volume_share20", "oi_median20", "log_volume", "log_oi_lag3",
    ]
    merged = pd.merge_asof(
        mandi.sort_values("date"),
        turkey[cols].sort_values("date").rename(columns={"date": "turkey_date"}),
        left_on="date",
        right_on="turkey_date",
        direction="backward",
        allow_exact_matches=False,
    )
    merged["turkey_age"] = (merged["date"] - merged["turkey_date"]).dt.days
    turkey_feature_cols = [c for c in cols if c != "date"]
    stale = merged["turkey_age"].gt(MAX_FEATURE_STALENESS_DAYS)
    merged.loc[stale, turkey_feature_cols] = np.nan
    merged["turkey_primary_quality"] = (
        merged["volume_share20"].ge(0.50)
        & merged["oi_median20"].ge(500)
        & merged["turkey_age"].le(3)
    ).astype(float)
    merged["turkey_curve_mark_quality"] = (
        merged["open_interest"].ge(100)
        & merged["turkey_age"].le(4)
    ).astype(float)
    return merged


def add_targets(data: pd.DataFrame) -> pd.DataFrame:
    dates = data["date"].to_numpy(dtype="datetime64[ns]")
    prices = data["8ANI"].to_numpy(float)
    for horizon in HORIZONS:
        endpoints = np.searchsorted(dates, dates + np.timedelta64(horizon, "D"), side="left")
        endpoint_dates = np.full(len(data), np.datetime64("NaT"), dtype="datetime64[ns]")
        endpoint_prices = np.full(len(data), np.nan)
        valid_idx = np.where(endpoints < len(data))[0]
        endpoint_dates[valid_idx] = dates[endpoints[valid_idx]]
        endpoint_prices[valid_idx] = prices[endpoints[valid_idx]]
        delay = (endpoint_dates - dates) / np.timedelta64(1, "D")
        valid = (delay >= horizon) & (delay <= horizon + TARGET_TOLERANCE_DAYS)
        data[f"target_end_{horizon}"] = pd.to_datetime(endpoint_dates).where(valid)
        data[f"target_ret_{horizon}"] = np.where(valid, np.log(endpoint_prices / prices), np.nan)
        data[f"target_change_{horizon}"] = np.where(valid, endpoint_prices - prices, np.nan)
        data[f"target_dir_{horizon}"] = np.where(
            valid,
            np.where(endpoint_prices > prices, 1, np.where(endpoint_prices < prices, -1, 0)),
            np.nan,
        )
    return data


FEATURE_FAMILIES = {
    "baseline": ["own_mom_5", "own_mom_10", "own_mom_20", "own_mom_30", "unchanged_20", "days_since_change", "ewma_vol", "monsoon"],
    "grade": ["plate_melt_z60", "plate_melt_z120", "plate_melt_rz60", "ten_melt_z60", "eight_melt_z60", "plate_1kgr_z60", "own_mom_10", "ewma_vol", "unchanged_20", "monsoon"],
    "turkey": ["turkey_mom_5", "turkey_mom_10", "turkey_mom_20", "turkey_mom_30", "turkey_rv20", "turkey_z60", "days_to_prompt", "turkey_age", "zero_volume", "log_oi_lag3", "own_mom_10", "ewma_vol"],
    "combined": ["plate_melt_z60", "plate_melt_z120", "ten_melt_z60", "eight_melt_z60", "own_mom_5", "own_mom_10", "own_mom_20", "unchanged_20", "days_since_change", "ewma_vol", "monsoon", "turkey_mom_5", "turkey_mom_10", "turkey_mom_20", "turkey_rv20", "turkey_z60", "days_to_prompt", "turkey_age", "zero_volume", "log_oi_lag3"],
}


def forward_call_metrics(pred_frame: pd.DataFrame) -> dict:
    rows = []
    for q in [0.50, 0.67, 0.75]:
        threshold = float(pred_frame["predicted"].abs().quantile(q))
        called = pred_frame[pred_frame["predicted"].abs() >= threshold]
        if len(called) == 0:
            continue
        direction_hit = float((np.sign(called["predicted"]) == np.sign(called["actual"])).mean())
        mean_signed = float(np.mean(np.sign(called["predicted"]) * called["actual"]))
        rows.append({
            "threshold_quantile": q,
            "threshold_log": threshold,
            "called_n": int(len(called)),
            "coverage": float(len(called) / len(pred_frame)),
            "direction_hit": direction_hit,
            "mean_signed_return": mean_signed,
        })
    return {"call_thresholds": rows}


def standardize_train_test(x_train: np.ndarray, x_test: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    med = np.nanmedian(x_train, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    x_train = np.where(np.isnan(x_train), med, x_train)
    x_test = np.where(np.isnan(x_test), med, x_test)
    q1 = np.nanpercentile(x_train, 1, axis=0)
    q99 = np.nanpercentile(x_train, 99, axis=0)
    x_train = np.clip(x_train, q1, q99)
    x_test = np.clip(x_test, q1, q99)
    mu = x_train.mean(axis=0)
    sigma = x_train.std(axis=0, ddof=1)
    sigma = np.where((sigma > 1e-10) & np.isfinite(sigma), sigma, 1.0)
    return (x_train - mu) / sigma, (x_test - mu) / sigma


def ridge_fit(x: np.ndarray, y: np.ndarray, alpha: float) -> tuple[np.ndarray, float]:
    y_mean = float(np.mean(y))
    xc = np.column_stack([np.ones(len(x)), x])
    penalty = np.eye(xc.shape[1]) * alpha
    penalty[0, 0] = 0
    beta = np.linalg.pinv(xc.T @ xc + penalty) @ (xc.T @ y)
    return beta, y_mean


def ridge_predict(beta: np.ndarray, x: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(x)), x]) @ beta


def choose_alpha(x: np.ndarray, y: np.ndarray) -> float:
    alphas = [0.1, 1.0, 10.0, 100.0]
    if len(y) < 80:
        return 10.0
    splits = [int(len(y) * q) for q in [0.60, 0.75, 0.90]]
    scores = []
    for alpha in alphas:
        fold_losses = []
        for split in splits:
            if split < 40 or split >= len(y):
                continue
            beta, _ = ridge_fit(x[:split], y[:split], alpha)
            pred = ridge_predict(beta, x[split:])
            fold_losses.append(np.mean(np.abs(y[split:] - pred)))
        scores.append((np.mean(fold_losses) if fold_losses else np.inf, alpha))
    return min(scores)[1]


@dataclass
class BacktestResult:
    family: str
    horizon: int
    predictions: pd.DataFrame
    summary: dict
    live: dict


def greedy_nonoverlap(frame: pd.DataFrame, horizon: int) -> pd.DataFrame:
    selected = []
    last_end = pd.Timestamp.min
    for idx, row in frame.sort_values("origin_date").iterrows():
        if row["origin_date"] >= last_end:
            selected.append(idx)
            last_end = row["target_end"]
    return frame.loc[selected].copy()


def stationary_block_bootstrap_diff(y: np.ndarray, pred: np.ndarray, base: np.ndarray, block: int, reps: int = 2000) -> tuple[float, float]:
    losses = np.abs(y - base) - np.abs(y - pred)
    n = len(losses)
    if n < 5:
        return np.nan, np.nan
    means = np.empty(reps)
    for b in range(reps):
        sample = []
        while len(sample) < n:
            start = RNG.integers(0, n)
            sample.extend(losses[(start + np.arange(block)) % n].tolist())
        means[b] = np.mean(sample[:n])
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def walk_forward(data: pd.DataFrame, horizon: int, family: str, features: list[str]) -> BacktestResult:
    target = f"target_ret_{horizon}"
    target_end = f"target_end_{horizon}"
    eligible = data[target].notna()
    if family in {"turkey", "combined"}:
        # The full curve-mark sample is exploratory; quality is reported separately.
        eligible &= data["turkey_curve_mark_quality"].eq(1)
    origins = data.index[eligible].to_numpy()
    rows = []
    min_train = 100 if family not in {"turkey", "combined"} else 40
    for pos in origins:
        origin_date = data.at[pos, "date"]
        matured = eligible & (data[target_end] < origin_date)
        train_idx = data.index[matured].to_numpy()
        if len(train_idx) < min_train:
            continue
        x_train = data.loc[train_idx, features].to_numpy(float)
        y_train = data.loc[train_idx, target].to_numpy(float)
        x_test = data.loc[[pos], features].to_numpy(float)
        x_train_s, x_test_s = standardize_train_test(x_train, x_test)
        alpha = choose_alpha(x_train_s, y_train)
        beta, _ = ridge_fit(x_train_s, y_train, alpha)
        pred = float(ridge_predict(beta, x_test_s)[0])
        baseline = float(np.median(y_train[-min(120, len(y_train)) :]))
        resid = y_train - ridge_predict(beta, x_train_s)
        scale = float(np.quantile(np.abs(resid), 0.80)) if len(resid) else np.nan
        rows.append({
            "origin_index": int(pos),
            "origin_date": origin_date,
            "target_end": data.at[pos, target_end],
            "actual": float(data.at[pos, target]),
            "predicted": pred,
            "baseline": baseline,
            "interval_half_80": scale,
            "alpha": alpha,
            "train_n": len(train_idx),
            "quality_primary": float(data.at[pos, "turkey_primary_quality"]) if "turkey_primary_quality" in data else np.nan,
        })
    pred_frame = pd.DataFrame(rows)
    if pred_frame.empty:
        return BacktestResult(family, horizon, pred_frame, {}, {})
    no = greedy_nonoverlap(pred_frame, horizon)
    y = pred_frame["actual"].to_numpy()
    pred = pred_frame["predicted"].to_numpy()
    base = pred_frame["baseline"].to_numpy()
    mae = float(np.mean(np.abs(y - pred)))
    base_mae = float(np.mean(np.abs(y - base)))
    direction = np.sign(pred)
    actual_direction = np.sign(y)
    called = direction != 0
    hit = float(np.mean(direction[called] == actual_direction[called])) if called.any() else np.nan
    no_y = no["actual"].to_numpy()
    no_pred = no["predicted"].to_numpy()
    no_base = no["baseline"].to_numpy()
    block = max(2, int(round(horizon / 3)))
    ci_low, ci_high = stationary_block_bootstrap_diff(y, pred, base, min(block, max(2, len(y) // 4)))
    cut_points = np.array_split(np.arange(len(pred_frame)), 3)
    thirds = [pred_frame.iloc[idx] for idx in cut_points if len(idx)]
    third_skills = [
        float(np.mean(np.abs(part["actual"] - part["baseline"])) - np.mean(np.abs(part["actual"] - part["predicted"])))
        for part in thirds if len(part)
    ]
    summary = {
        "family": family,
        "horizon": horizon,
        "raw_oos_n": int(len(pred_frame)),
        "nonoverlap_n": int(len(no)),
        "mae_log": mae,
        "baseline_mae_log": base_mae,
        "mae_skill_log": base_mae - mae,
        "mae_skill_pct": (base_mae - mae) / base_mae if base_mae else np.nan,
        "direction_hit": hit,
        "nonoverlap_mae_skill_log": float(np.mean(np.abs(no_y - no_base)) - np.mean(np.abs(no_y - no_pred))) if len(no) else np.nan,
        "bootstrap_skill_ci_low": ci_low,
        "bootstrap_skill_ci_high": ci_high,
        "third_skill_min": min(third_skills) if third_skills else np.nan,
        "third_skill_median": float(np.median(third_skills)) if third_skills else np.nan,
        "primary_quality_oos_n": int(pred_frame["quality_primary"].eq(1).sum()),
        **forward_call_metrics(pred_frame),
    }

    # Final live fit uses only labels fully matured before the last quote.
    live_pos = data.index[-1]
    live_date = data.at[live_pos, "date"]
    matured = eligible & (data[target_end] < live_date)
    train_idx = data.index[matured].to_numpy()
    x_train = data.loc[train_idx, features].to_numpy(float)
    y_train = data.loc[train_idx, target].to_numpy(float)
    x_live = data.loc[[live_pos], features].to_numpy(float)
    x_train_s, x_live_s = standardize_train_test(x_train, x_live)
    alpha = choose_alpha(x_train_s, y_train)
    beta, _ = ridge_fit(x_train_s, y_train, alpha)
    live_pred = float(ridge_predict(beta, x_live_s)[0])
    live_resid = y_train - ridge_predict(beta, x_train_s)
    half80 = float(np.quantile(np.abs(live_resid), 0.80))
    current_price = float(data.at[live_pos, "8ANI"])
    live = {
        "family": family,
        "horizon": horizon,
        "as_of": str(live_date.date()),
        "current_price": current_price,
        "predicted_log_return": live_pred,
        "predicted_pct": math.expm1(live_pred),
        "predicted_price": current_price * math.exp(live_pred),
        "lower80_price": current_price * math.exp(live_pred - half80),
        "upper80_price": current_price * math.exp(live_pred + half80),
        "train_n": int(len(train_idx)),
        "alpha": alpha,
        "turkey_primary_quality": bool(data.at[live_pos, "turkey_primary_quality"] == 1),
        "turkey_age": None if pd.isna(data.at[live_pos, "turkey_age"]) else float(data.at[live_pos, "turkey_age"]),
    }
    return BacktestResult(family, horizon, pred_frame, summary, live)


def null_max_skill(data: pd.DataFrame, results: list[BacktestResult], reps: int = 1000) -> dict:
    # Selection benchmark across the actually tested family/horizon set.
    observed = [r.summary.get("mae_skill_log", np.nan) for r in results]
    observed_max = float(np.nanmax(observed))
    null_maxima = []
    for _ in range(reps):
        skills = []
        for r in results:
            f = r.predictions
            if len(f) < 10:
                continue
            y = f["actual"].to_numpy()
            base = f["baseline"].to_numpy()
            pred = f["predicted"].to_numpy()
            shift = int(RNG.integers(max(2, len(y) // 10), max(3, len(y) - max(2, len(y) // 10))))
            shuffled_pred = np.roll(pred, shift)
            skills.append(float(np.mean(np.abs(y - base)) - np.mean(np.abs(y - shuffled_pred))))
        if skills:
            null_maxima.append(max(skills))
    null = np.array(null_maxima)
    return {
        "candidate_count": len(results),
        "observed_best_skill_log": observed_max,
        "expected_best_null_skill_log": float(np.mean(null)),
        "null_95_skill_log": float(np.quantile(null, 0.95)),
        "selection_adjusted_p": float((1 + np.sum(null >= observed_max)) / (1 + len(null))),
        "deflated_skill_log": observed_max - float(np.quantile(null, 0.95)),
    }


def main() -> None:
    mandi = load_mandi()
    turkey = load_turkey()
    panel = add_targets(asof_turkey(mandi, turkey))
    panel.to_csv(OUTPUTS / "master_panel.csv", index=False)

    results: list[BacktestResult] = []
    for horizon in HORIZONS:
        for family, features in FEATURE_FAMILIES.items():
            result = walk_forward(panel, horizon, family, features)
            results.append(result)
            if not result.predictions.empty:
                result.predictions.to_csv(OUTPUTS / f"oos_{family}_{horizon}d.csv", index=False)

    summaries = pd.DataFrame([r.summary for r in results if r.summary])
    live = pd.DataFrame([r.live for r in results if r.live])

    # Pick one family per horizon by median/robust gate, not raw best alone.
    selected_rows = []
    for horizon in HORIZONS:
        candidates = summaries[summaries["horizon"] == horizon].copy()
        candidates["validated_gate"] = (
            (candidates["nonoverlap_n"] >= 20)
            & (candidates["bootstrap_skill_ci_low"] > 0)
            & (candidates["third_skill_min"] >= 0)
        )
        candidates["rank_score"] = (
            candidates["nonoverlap_mae_skill_log"].fillna(-999)
            + 0.5 * candidates["mae_skill_log"].fillna(-999)
            + 0.25 * candidates["third_skill_min"].fillna(-999)
        )
        eligible = candidates[candidates["validated_gate"]]
        chosen = (eligible if len(eligible) else candidates).sort_values("rank_score", ascending=False).iloc[0]
        chosen_live = live[(live["horizon"] == horizon) & (live["family"] == chosen["family"])].iloc[0]
        status = "VALIDATED" if bool(chosen["validated_gate"]) else ("PROVISIONAL" if chosen["nonoverlap_n"] >= 10 else "NO CALL - LOW N")
        # Require a material prediction beyond half the empirical 80% half-band.
        low = chosen_live["lower80_price"]
        high = chosen_live["upper80_price"]
        current = chosen_live["current_price"]
        if status == "VALIDATED" and low > current:
            call = "UP / HOLD"
        elif status == "VALIDATED" and high < current:
            call = "DOWN / SELL"
        else:
            call = "NO CALL"
        selected_rows.append({
            **chosen.to_dict(),
            **{f"live_{k}": v for k, v in chosen_live.to_dict().items()},
            "status": status,
            "call": call,
        })
    selected = pd.DataFrame(selected_rows)

    search_adjustment = null_max_skill(panel, results)
    summaries.to_csv(OUTPUTS / "backtest_summary.csv", index=False)
    live.to_csv(OUTPUTS / "live_forecasts_all_models.csv", index=False)
    selected.to_csv(OUTPUTS / "selected_horizon_forecasts.csv", index=False)

    quality = {
        "mandi_rows": int(len(mandi)),
        "mandi_first": str(mandi["date"].min().date()),
        "mandi_last": str(mandi["date"].max().date()),
        "large_gaps_days": mandi["date"].diff().dt.days[mandi["date"].diff().dt.days > 14].astype(int).tolist(),
        "continuous_segment_rows": int((mandi["date"] >= pd.Timestamp("2024-09-18")).sum()),
        "turkey_rows": int(len(turkey)),
        "turkey_first": str(turkey["date"].min().date()),
        "turkey_last": str(turkey["date"].max().date()),
        "turkey_zero_volume_rate": float(turkey["volume"].eq(0).mean()),
        "turkey_zero_oi_rows": int(turkey["open_interest"].eq(0).sum()),
        "strict_prior_matches": int(panel["turkey_date"].notna().sum()),
        "strict_prior_under_4d": int(panel["turkey_age"].le(4).sum()),
        "primary_quality_rows": int(panel["turkey_primary_quality"].eq(1).sum()),
        "target_counts": {str(h): int(panel[f"target_ret_{h}"].notna().sum()) for h in HORIZONS},
        "search_adjustment": search_adjustment,
    }
    (OUTPUTS / "study_metadata.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
    print(json.dumps({"quality": quality, "selected": selected.to_dict(orient="records")}, indent=2, default=str))


if __name__ == "__main__":
    main()
