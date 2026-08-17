from __future__ import annotations

"""Native-frequency, point-in-time screens and incremental OOS tests for audited factors."""

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

import forecast_study_v3 as core


OUT = core.ROOT / "outputs" / "global_factor_test"
OUT.mkdir(parents=True, exist_ok=True)
ENGINE = core.INPUTS / "engine_context"
DOWNLOADS = Path(r"C:\Users\demos\Downloads")
HORIZONS = core.HORIZONS
MONTHLY_HORIZONS = [30, 60, 90]
SEED = 20260812 + 177
REPS = 2000
RIDGE_ALPHA = 10.0
RNG = np.random.default_rng(SEED)


@dataclass
class Factor:
    name: str
    frame: pd.DataFrame
    frequency: str
    quality: str
    causal_test: bool
    min_train: int
    live_max_age: int
    horizons: list[int]


def read_rows(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        return list(csv.reader(handle))


def parse_simple_engine_csv(path: Path, date_column: str, value_column: str) -> pd.DataFrame:
    rows = read_rows(path)
    header = next(i for i, row in enumerate(rows) if row and row[0].strip() == date_column)
    output = []
    for row in rows[header + 1 :]:
        if len(row) < 2 or not row[0].strip():
            break
        output.append((row[0].strip(), row[1].replace(",", "").strip()))
    frame = pd.DataFrame(output, columns=["period", "value"])
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame.dropna(subset=["value"])


def parse_section_months(path: Path, marker: str, value_index: int = 1) -> pd.DataFrame:
    rows = read_rows(path)
    start = next(i for i, row in enumerate(rows) if row and marker in row[0])
    output: list[tuple[str, str]] = []
    seen_header = False
    for row in rows[start + 1 :]:
        first = row[0].strip() if row else ""
        if first == "Month":
            seen_header = True
            continue
        if seen_header and first and not pd.Series([first]).str.match(r"^\d{4}-\d{2}$").iloc[0]:
            break
        if seen_header and len(row) > value_index and pd.Series([first]).str.match(r"^\d{4}-\d{2}$").iloc[0]:
            output.append((first, row[value_index].replace(",", "").strip()))
    frame = pd.DataFrame(output, columns=["period", "value"])
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame.dropna(subset=["value"])


def parse_turkey_monthly() -> pd.DataFrame:
    rows = read_rows(ENGINE / "turkey_hms_8020.csv")
    start = next(i for i, row in enumerate(rows) if row and row[0].startswith("BREAKTHROUGH"))
    stop = next(i for i, row in enumerate(rows[start + 1 :], start + 1) if row and row[0].startswith("REAL WEEKLY"))
    output = []
    for row in rows[start:stop]:
        if len(row) >= 3 and pd.Series([row[0].strip()]).str.match(r"^\d{4}-\d{2}$").iloc[0]:
            output.append((row[0].strip(), row[2].replace(",", "").strip()))
    frame = pd.DataFrame(output, columns=["period", "value"])
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame.dropna().sort_values("period").drop_duplicates("period", keep="last")


def monthly_momentum(frame: pd.DataFrame, level_signal: bool = False) -> pd.DataFrame:
    output = frame.copy()
    output["period_date"] = pd.to_datetime(output["period"] + "-01")
    output["available_date"] = output["period_date"] + pd.offsets.MonthEnd(0)
    if level_signal:
        output["signal"] = np.log1p(output["value"])
    else:
        elapsed = (
            (output["period_date"].dt.year - output["period_date"].shift().dt.year) * 12
            + output["period_date"].dt.month - output["period_date"].shift().dt.month
        )
        output["signal"] = np.log(output["value"] / output["value"].shift()) / elapsed.where(elapsed > 0)
    return output[["available_date", "value", "signal"]].dropna(subset=["signal"])


def weekly_hrc(lag_weeks: int = 1) -> pd.DataFrame:
    raw = parse_simple_engine_csv(ENGINE / "china_hrc_fob.csv", "Date", "Price ($/t)")
    raw["available_date"] = pd.to_datetime(raw["period"], errors="coerce")
    raw = raw.sort_values("available_date")
    raw["signal"] = np.log(raw["value"] / raw["value"].shift(lag_weeks))
    # Require an actual native interval rather than silently bridging a hole.
    elapsed = (raw["available_date"] - raw["available_date"].shift(lag_weeks)).dt.days
    raw.loc[elapsed.ne(7 * lag_weeks), "signal"] = np.nan
    return raw[["available_date", "value", "signal"]].dropna(subset=["signal"])


def daily_price(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame["available_date"] = pd.to_datetime(frame["Time"], errors="coerce")
    frame["value"] = pd.to_numeric(frame["Latest"], errors="coerce")
    frame = frame.dropna(subset=["available_date", "value"]).sort_values("available_date").drop_duplicates("available_date")
    frame["signal"] = core.calendar_log_change(frame["available_date"], frame["value"], 10, tolerance=4)
    return frame[["available_date", "value", "signal"]].dropna(subset=["signal"])


def daily_spread() -> pd.DataFrame:
    rebar = pd.read_csv(DOWNLOADS / "r-u26_daily_historical-data-08-11-2026.csv")
    scrap = pd.read_csv(DOWNLOADS / "c-u26_daily_historical-data-08-11-2026.csv")
    for frame in (rebar, scrap):
        frame["available_date"] = pd.to_datetime(frame["Time"], errors="coerce")
        frame["Latest"] = pd.to_numeric(frame["Latest"], errors="coerce")
    merged = rebar[["available_date", "Latest"]].merge(
        scrap[["available_date", "Latest"]], on="available_date", suffixes=("_rebar", "_scrap")
    ).dropna().sort_values("available_date")
    merged["value"] = np.log(merged["Latest_rebar"] / merged["Latest_scrap"])
    merged["signal"] = core.calendar_log_change(
        merged["available_date"], np.exp(merged["value"]), 10, tolerance=4
    )
    return merged[["available_date", "value", "signal"]].dropna(subset=["signal"])


def supply_monthly(column: str) -> pd.DataFrame:
    path = core.INPUTS / "external" / "alangtoday_monthly_beachings_2016_2026_asof_20260812T100336Z.csv"
    raw = pd.read_csv(path)
    raw["period"] = raw["period_month"].astype(str)
    raw["value"] = pd.to_numeric(raw[column], errors="coerce")
    return monthly_momentum(raw[["period", "value"]], level_signal=True)


def build_factors() -> list[Factor]:
    usd_month = monthly_momentum(parse_simple_engine_csv(ENGINE / "usd_inr.csv", "Month", "USD/INR Avg"))
    bdi_month = monthly_momentum(parse_section_months(ENGINE / "supply_substitutes.csv", "BALTIC DRY INDEX - FULL"))
    iron_month = monthly_momentum(parse_section_months(ENGINE / "supply_substitutes.csv", "IRON ORE CFR CHINA"))
    coal_month = monthly_momentum(parse_section_months(ENGINE / "supply_substitutes.csv", "COKING COAL - SGX"))
    turkey_month = monthly_momentum(parse_turkey_monthly())
    return [
        Factor("usd_inr_monthly", usd_month, "monthly", "monthly average", True, 10, 45, MONTHLY_HORIZONS),
        Factor("bdi_monthly", bdi_month, "monthly", "approximate chart-read", True, 10, 45, MONTHLY_HORIZONS),
        Factor("iron_ore_monthly", iron_month, "sparse monthly", "approximate chart-read; irregular gaps", True, 8, 100, MONTHLY_HORIZONS),
        Factor("coking_coal_monthly", coal_month, "sparse monthly", "approximate chart-read; irregular gaps", True, 8, 100, MONTHLY_HORIZONS),
        Factor("turkey_scrap_monthly", turkey_month, "monthly", "approximate chart-read", True, 10, 45, MONTHLY_HORIZONS),
        Factor("china_hrc_weekly_mom1w", weekly_hrc(1), "weekly", "audited weekly price; roll method opaque", True, 26, 10, HORIZONS),
        Factor("china_hrc_weekly_mom4w", weekly_hrc(4), "weekly", "audited weekly price; roll method opaque", True, 26, 10, HORIZONS),
        Factor("usd_inr_daily_fragment", daily_price(DOWNLOADS / "usdinr_price-history-08-11-2026.csv"), "daily", "liquid but only May-Aug 2026", True, 30, 4, HORIZONS),
        Factor("coking_coal_yqu26", daily_price(DOWNLOADS / "yqu26_price-history-08-11-2026.csv"), "daily fixed contract", "liquid but short and maturity-dependent", True, 30, 4, HORIZONS),
        Factor("china_hrc_v7q26", daily_price(DOWNLOADS / "v7q26_price-history-08-11-2026.csv"), "daily fixed contract", "short; mostly curve marks", True, 30, 4, HORIZONS),
        Factor("iron_ore_trq26", daily_price(DOWNLOADS / "trq26_price-history-08-11-2026.csv"), "daily fixed contract", "all zero volume/OI/range; assessment curve", True, 60, 4, HORIZONS),
        Factor("turkey_rebar_ru26", daily_price(DOWNLOADS / "r-u26_daily_historical-data-08-11-2026.csv"), "daily fixed contract", "95% zero volume; maturity-dependent", True, 60, 4, HORIZONS),
        Factor("turkey_rebar_scrap_spread_u26", daily_spread(), "daily matched fixed contracts", "matched prompt but thin/maturity-dependent", True, 60, 4, HORIZONS),
        Factor("alang_beached_ldt", supply_monthly("ldt_beached_metric_tonnes"), "monthly", "current-vintage; release timestamps unknown", False, 10, 45, MONTHLY_HORIZONS),
        Factor("alang_beached_ships", supply_monthly("ships_beached_count"), "monthly", "current-vintage; release timestamps unknown", False, 10, 45, MONTHLY_HORIZONS),
    ]


def attach_factor(panel: pd.DataFrame, factor: Factor) -> pd.DataFrame:
    dates = panel["date"].to_numpy(dtype="datetime64[ns]")
    rows = []
    for item in factor.frame.sort_values("available_date").itertuples(index=False):
        available = pd.Timestamp(item.available_date)
        position = int(np.searchsorted(dates, np.datetime64(available), side="right"))
        if position >= len(panel):
            continue
        row = {
            "factor": factor.name,
            "frequency": factor.frequency,
            "quality": factor.quality,
            "causal_test": factor.causal_test,
            "available_date": available,
            "origin_index": int(panel.index[position]),
            "origin_date": panel.at[position, "date"],
            "factor_value": float(item.value),
            "signal": float(item.signal),
            "plate_melt_z60": float(panel.at[position, "plate_melt_z60"]),
        }
        assert row["available_date"] < row["origin_date"]
        for horizon in factor.horizons:
            row[f"target_ret_{horizon}"] = panel.at[position, f"target_ret_{horizon}"]
            row[f"target_dir_{horizon}"] = panel.at[position, f"target_dir_{horizon}"]
            row[f"target_end_{horizon}"] = panel.at[position, f"target_end_{horizon}"]
        rows.append(row)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    # Multiple source observations can map to the same sparse Mandi quote; use only the latest known one.
    return frame.sort_values("available_date").drop_duplicates("origin_date", keep="last").reset_index(drop=True)


def corr(x: np.ndarray, y: np.ndarray, rank: bool = False) -> float:
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    valid = np.isfinite(x) & np.isfinite(y)
    x, y = x[valid], y[valid]
    if len(x) < 3 or np.std(x) <= 1e-15 or np.std(y) <= 1e-15:
        return np.nan
    if rank:
        x = pd.Series(x).rank(method="average").to_numpy()
        y = pd.Series(y).rank(method="average").to_numpy()
    return float(np.corrcoef(x, y)[0, 1])


def circular_indices(n: int, block: int) -> np.ndarray:
    output: list[int] = []
    while len(output) < n:
        start = int(RNG.integers(0, n))
        output.extend(((start + np.arange(block)) % n).tolist())
    return np.asarray(output[:n], int)


def bootstrap_ci(values: np.ndarray, block: int) -> tuple[float, float, float, np.ndarray]:
    values = np.asarray(values, float)
    if len(values) < 5:
        return np.nan, np.nan, np.nan, np.full(REPS, np.nan)
    means = np.array([np.mean(values[circular_indices(len(values), block)]) for _ in range(REPS)])
    return float(np.quantile(means, .025)), float(np.quantile(means, .975)), float(np.std(means, ddof=1)), means


def correlation_ci(x: np.ndarray, y: np.ndarray, block: int, rank: bool) -> tuple[float, float]:
    if len(x) < 8:
        return np.nan, np.nan
    draws = []
    for _ in range(REPS):
        idx = circular_indices(len(x), block)
        draws.append(corr(x[idx], y[idx], rank=rank))
    draws = np.asarray(draws, float)
    draws = draws[np.isfinite(draws)]
    return (float(np.quantile(draws, .025)), float(np.quantile(draws, .975))) if len(draws) else (np.nan, np.nan)


def effective_n(frame: pd.DataFrame, horizon: int) -> int:
    count = 0
    last_end = pd.Timestamp.min
    for row in frame.sort_values("origin_date").itertuples(index=False):
        end = getattr(row, f"target_end_{horizon}", getattr(row, "target_end", pd.NaT))
        if row.origin_date >= last_end:
            count += 1
            last_end = end
    return count


def block_for(frame: pd.DataFrame, horizon: int) -> int:
    spacing = frame["origin_date"].diff().dt.days.dropna()
    median = float(spacing.median()) if len(spacing) else 1.0
    return min(max(2, int(math.ceil(horizon / max(median, 1.0)))), max(2, len(frame) // 3))


def fit_processor(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    median = np.nanmedian(x, axis=0)
    median = np.where(np.isfinite(median), median, 0.0)
    filled = np.where(np.isfinite(x), x, median)
    lo, hi = np.quantile(filled, .01, axis=0), np.quantile(filled, .99, axis=0)
    clipped = np.clip(filled, lo, hi)
    mean, scale = clipped.mean(axis=0), clipped.std(axis=0, ddof=1)
    scale = np.where(np.isfinite(scale) & (scale > 1e-12), scale, 1.0)
    return median, lo, hi, np.vstack([mean, scale])


def apply_processor(x: np.ndarray, processor: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]) -> np.ndarray:
    median, lo, hi, stats = processor
    filled = np.where(np.isfinite(x), x, median)
    return (np.clip(filled, lo, hi) - stats[0]) / stats[1]


def ridge_fit(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    design = np.column_stack([np.ones(len(x)), x])
    penalty = np.eye(design.shape[1]) * RIDGE_ALPHA
    penalty[0, 0] = 0
    return np.linalg.pinv(design.T @ design + penalty) @ (design.T @ y)


def predict_one(beta: np.ndarray, x: np.ndarray) -> float:
    return float(np.r_[1.0, x] @ beta)


def test_factor(frame: pd.DataFrame, factor: Factor, horizon: int) -> pd.DataFrame:
    target = f"target_ret_{horizon}"
    target_dir = f"target_dir_{horizon}"
    target_end = f"target_end_{horizon}"
    eligible = frame.dropna(subset=[target, target_dir, target_end, "plate_melt_z60", "signal"]).sort_values("origin_date")
    rows = []
    for position, origin in eligible.iterrows():
        train = eligible[eligible[target_end] < origin["origin_date"]]
        if len(train) < factor.min_train:
            continue
        assert (train[target_end] < origin["origin_date"]).all()
        y = train[target].to_numpy(float)
        classes = train[target_dir].to_numpy(int)
        counts = np.array([(classes == label).sum() for label in core.CLASSES], float)
        frequency = (counts + 1) / (len(classes) + 3)

        xb_raw = train[["plate_melt_z60"]].to_numpy(float)
        xc_raw = train[["plate_melt_z60", "signal"]].to_numpy(float)
        pb, pc = fit_processor(xb_raw), fit_processor(xc_raw)
        xb, xc = apply_processor(xb_raw, pb), apply_processor(xc_raw, pc)
        xb_test = apply_processor(origin[["plate_melt_z60"]].to_numpy(float).reshape(1, -1), pb)[0]
        xc_test = apply_processor(origin[["plate_melt_z60", "signal"]].to_numpy(float).reshape(1, -1), pc)[0]
        beta_b, beta_c = ridge_fit(xb, y), ridge_fit(xc, y)

        # Direction head: one ridge per class, projected back onto the simplex exactly as v3.
        one_hot = core.one_hot(classes)
        beta_class = np.column_stack([ridge_fit(xc, one_hot[:, j]) for j in range(3)])
        raw_probability = np.r_[1.0, xc_test] @ beta_class
        probability = core.class_probabilities(raw_probability.reshape(1, -1), frequency)[0]
        rows.append({
            "factor": factor.name,
            "horizon": horizon,
            "origin_date": origin["origin_date"],
            "target_end": origin[target_end],
            "actual": float(origin[target]),
            "actual_class": int(origin[target_dir]),
            "plate_prediction": predict_one(beta_b, xb_test),
            "candidate_prediction": predict_one(beta_c, xc_test),
            "prob_down": probability[0],
            "prob_flat": probability[1],
            "prob_up": probability[2],
            "freq_down": frequency[0],
            "freq_flat": frequency[1],
            "freq_up": frequency[2],
            "train_n": len(train),
        })
    return pd.DataFrame(rows)


def summarize_oos(predictions: pd.DataFrame) -> tuple[pd.DataFrame, dict[tuple[str, int], dict]]:
    rows = []
    bootstrap_store: dict[tuple[str, int], dict] = {}
    for (factor, horizon), group in predictions.groupby(["factor", "horizon"], sort=False):
        group = group.sort_values("origin_date").reset_index(drop=True)
        actual = group["actual"].to_numpy(float)
        plate = group["plate_prediction"].to_numpy(float)
        candidate = group["candidate_prediction"].to_numpy(float)
        incremental = np.abs(actual - plate) - np.abs(actual - candidate)
        zero_skill = np.abs(actual) - np.abs(actual - candidate)
        probabilities = group[["prob_down", "prob_flat", "prob_up"]].to_numpy(float)
        frequency = group[["freq_down", "freq_flat", "freq_up"]].to_numpy(float)
        classes = group["actual_class"].to_numpy(int)
        brier_skill = core.brier_loss(classes, frequency) - core.brier_loss(classes, probabilities)
        block = block_for(group, int(horizon))
        inc_lo, inc_hi, inc_se, inc_draws = bootstrap_ci(incremental, block)
        zero_lo, zero_hi, _, _ = bootstrap_ci(zero_skill, block)
        br_lo, br_hi, _, _ = bootstrap_ci(brier_skill, block)
        bootstrap_store[(factor, int(horizon))] = {
            "observed": float(np.mean(incremental)), "se": inc_se,
            "centered": inc_draws - np.mean(incremental), "n": len(group), "block": block,
        }
        rows.append({
            "factor": factor,
            "horizon": int(horizon),
            "oos_raw_n": len(group),
            "oos_effective_n": effective_n(group, int(horizon)),
            "first_oos": group["origin_date"].min(),
            "last_oos": group["origin_date"].max(),
            "candidate_mae": float(np.mean(np.abs(actual - candidate))),
            "zero_mae": float(np.mean(np.abs(actual))),
            "plate_mae": float(np.mean(np.abs(actual - plate))),
            "mae_skill_zero": float(np.mean(zero_skill)),
            "mae_skill_zero_ci_low": zero_lo,
            "mae_skill_zero_ci_high": zero_hi,
            "incremental_mae_skill_vs_plate": float(np.mean(incremental)),
            "incremental_ci_low": inc_lo,
            "incremental_ci_high": inc_hi,
            "brier_skill_frequency": float(np.mean(brier_skill)),
            "brier_ci_low": br_lo,
            "brier_ci_high": br_hi,
        })
    return pd.DataFrame(rows), bootstrap_store


def max_null(store: dict[tuple[str, int], dict]) -> pd.DataFrame:
    usable = {key: value for key, value in store.items() if np.isfinite(value["se"]) and value["se"] > 1e-12}
    max_t = np.full(REPS, -np.inf)
    for value in usable.values():
        max_t = np.maximum(max_t, value["centered"] / value["se"])
    rows = []
    for (factor, horizon), value in store.items():
        se = value["se"]
        statistic = value["observed"] / se if np.isfinite(se) and se > 1e-12 else np.nan
        adjusted = float((1 + np.sum(max_t >= statistic)) / (1 + REPS)) if np.isfinite(statistic) else np.nan
        rows.append({
            "factor": factor, "horizon": horizon, "observed_incremental_skill": value["observed"],
            "bootstrap_se": se, "studentized_stat": statistic, "max_null_adjusted_p": adjusted,
            "candidate_count": len(usable), "oos_n": value["n"], "block": value["block"],
        })
    return pd.DataFrame(rows)


def live_forecasts(panel: pd.DataFrame, factors: list[Factor], attached: dict[str, pd.DataFrame]) -> pd.DataFrame:
    live = panel.iloc[-1]
    rows = []
    for factor in factors:
        frame = attached[factor.name]
        if frame.empty or not factor.causal_test:
            continue
        # Use the latest factor observation strictly before the live Mandi quote.
        source = factor.frame[factor.frame["available_date"] < live["date"]].sort_values("available_date")
        if source.empty:
            continue
        latest = source.iloc[-1]
        age = int((live["date"] - latest["available_date"]).days)
        for horizon in factor.horizons:
            target, target_end = f"target_ret_{horizon}", f"target_end_{horizon}"
            train = frame.dropna(subset=[target, target_end, "plate_melt_z60", "signal"])
            train = train[train[target_end] < live["date"]].sort_values("origin_date")
            if len(train) < factor.min_train:
                continue
            x = train[["plate_melt_z60", "signal"]].to_numpy(float)
            processor = fit_processor(x)
            x_fit = apply_processor(x, processor)
            beta = ridge_fit(x_fit, train[target].to_numpy(float))
            x_live = apply_processor(np.array([[live["plate_melt_z60"], latest["signal"]]], float), processor)[0]
            prediction = predict_one(beta, x_live)
            rows.append({
                "as_of": live["date"], "factor": factor.name, "horizon": horizon,
                "current_price": live["8ANI"], "source_date": latest["available_date"], "source_age_days": age,
                "source_stale": age > factor.live_max_age, "predicted_log_return": prediction,
                "predicted_pct": math.expm1(prediction), "predicted_price": live["8ANI"] * math.exp(prediction),
                "train_raw_n": len(train), "quality": factor.quality,
            })
    return pd.DataFrame(rows)


def main() -> None:
    panel, _ = core.build_panel()
    panel = core.add_targets(panel)
    factors = build_factors()
    attached = {factor.name: attach_factor(panel, factor) for factor in factors}

    correlation_rows = []
    prediction_parts = []
    inventory_rows = []
    for factor in factors:
        frame = attached[factor.name]
        inventory_rows.append({
            "factor": factor.name, "frequency": factor.frequency, "quality": factor.quality,
            "source_signal_n": len(factor.frame), "matched_native_origins": len(frame),
            "first_source": factor.frame["available_date"].min() if len(factor.frame) else pd.NaT,
            "last_source": factor.frame["available_date"].max() if len(factor.frame) else pd.NaT,
            "causal_model_eligible": factor.causal_test,
        })
        for horizon in factor.horizons:
            valid = frame.dropna(subset=[f"target_ret_{horizon}", f"target_end_{horizon}", "signal"]).copy()
            if valid.empty:
                continue
            x = valid["signal"].to_numpy(float)
            y = valid[f"target_ret_{horizon}"].to_numpy(float)
            block = block_for(valid, horizon)
            p_lo, p_hi = correlation_ci(x, y, block, rank=False)
            s_lo, s_hi = correlation_ci(x, y, block, rank=True)
            correlation_rows.append({
                "factor": factor.name, "frequency": factor.frequency, "quality": factor.quality,
                "causal_model_eligible": factor.causal_test, "horizon": horizon,
                "native_n": len(valid), "effective_nonoverlap_n": effective_n(valid, horizon),
                "pearson": corr(x, y), "pearson_ci_low": p_lo, "pearson_ci_high": p_hi,
                "spearman": corr(x, y, rank=True), "spearman_ci_low": s_lo, "spearman_ci_high": s_hi,
                "block_native_origins": block,
            })
            if factor.causal_test:
                tested = test_factor(frame, factor, horizon)
                if not tested.empty:
                    prediction_parts.append(tested)

    correlations = pd.DataFrame(correlation_rows)
    predictions = pd.concat(prediction_parts, ignore_index=True) if prediction_parts else pd.DataFrame()
    summaries, store = summarize_oos(predictions)
    adjustment = max_null(store)
    scoreboard = correlations.merge(summaries, on=["factor", "horizon"], how="left").merge(
        adjustment[["factor", "horizon", "max_null_adjusted_p"]], on=["factor", "horizon"], how="left"
    )
    live = live_forecasts(panel, factors, attached)

    pd.DataFrame(inventory_rows).to_csv(OUT / "factor_inventory.csv", index=False)
    correlations.to_csv(OUT / "native_correlation_screen.csv", index=False)
    predictions.to_csv(OUT / "purged_oos_predictions.csv", index=False)
    summaries.to_csv(OUT / "incremental_oos_summary.csv", index=False)
    adjustment.to_csv(OUT / "incremental_max_null.csv", index=False)
    scoreboard.to_csv(OUT / "factor_scoreboard.csv", index=False)
    live.to_csv(OUT / "live_factor_forecasts.csv", index=False)
    metadata = {
        "seed": SEED, "bootstrap_reps": REPS, "ridge_alpha_fixed": RIDGE_ALPHA,
        "monthly_rule": "one native month observation, available only after month-end; no daily forward-fill",
        "weekly_rule": "one native weekly observation; no daily interpolation",
        "daily_rule": "source close becomes eligible only for a strictly later Mandi date",
        "feature_rules": {
            "monthly_prices": "one-native-period log change normalized by elapsed months",
            "weekly_hrc": "four-week log change requiring exactly 28 elapsed days",
            "daily_prices": "10-calendar-day log change, max four-day lag tolerance",
            "supply": "log level; descriptive only because historical release timestamps are unknown",
        },
        "oos": "purged expanding ridge, fixed alpha, candidate plate-melt plus factor vs same-origin plate-melt only",
        "multiple_testing": "maximum studentized centered moving-block bootstrap over every estimable factor-horizon incremental MAE test",
        "current_snapshot_supply": "not tested: one snapshot cannot identify a historical forecast relationship",
    }
    (OUT / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
