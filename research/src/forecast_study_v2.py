from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "inputs"
OUTPUTS = ROOT / "outputs" / "v2"
OUTPUTS.mkdir(parents=True, exist_ok=True)

HORIZONS = [5, 10, 15, 30, 45, 60, 90]
CLASSES = np.array([-1, 0, 1], dtype=int)
CLASS_NAMES = ["down", "flat", "up"]
TARGET_TOLERANCE_DAYS = 4
MAX_STALENESS_DAYS = 4
MIN_RAW_TRAIN = 80
OOS_ORIGIN_SPACING_DAYS = 7
ALPHAS = [1.0, 10.0, 100.0]
BOOTSTRAP_REPS = 600
MAX_NULL_REPS = 600
SEED = 20260812
RNG = np.random.default_rng(SEED)


INTERNAL_FEATURES = [
    "plate_melt_z60",
    "own_mom_10d",
    "ewma_vol",
    "unchanged_20",
]
LOCAL_FEATURES = [
    "local_ingot_mom10",
    "local_tmt_mom10",
    "scrap_ingot_z60",
]
TURKEY_FEATURES = [
    "turkey_mom5",
    "turkey_mom10",
    "turkey_rv10",
]
COMBINED_FEATURES = INTERNAL_FEATURES + LOCAL_FEATURES + TURKEY_FEATURES

MODEL_FEATURES = {
    "baseline": [],
    "internal": INTERNAL_FEATURES,
    "local": INTERNAL_FEATURES + LOCAL_FEATURES,
    "turkey": INTERNAL_FEATURES + TURKEY_FEATURES,
    "combined": COMBINED_FEATURES,
    "nonlinear": COMBINED_FEATURES,
}
MODEL_ORDER = list(MODEL_FEATURES)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def as_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype(float)


def rolling_z_by_segment(
    frame: pd.DataFrame,
    column: str,
    window: int,
    segment: str = "continuous_segment",
) -> pd.Series:
    out = pd.Series(np.nan, index=frame.index, dtype=float)
    for _, group in frame.groupby(segment, sort=False):
        values = group[column].astype(float)
        past = values.shift(1)
        mean = past.rolling(window, min_periods=window).mean()
        std = past.rolling(window, min_periods=window).std(ddof=1)
        out.loc[group.index] = ((values - mean) / std.replace(0, np.nan)).to_numpy()
    return out


def calendar_log_change(
    dates: pd.Series,
    prices: pd.Series,
    days: int,
    tolerance: int = 4,
) -> pd.Series:
    date_values = dates.to_numpy(dtype="datetime64[ns]")
    price_values = prices.to_numpy(float)
    reference = date_values - np.timedelta64(days, "D")
    positions = np.searchsorted(date_values, reference, side="right") - 1
    output = np.full(len(dates), np.nan)
    valid = positions >= 0
    indices = np.where(valid)[0]
    lag_days = np.full(len(dates), np.nan)
    lag_days[indices] = (reference[indices] - date_values[positions[indices]]) / np.timedelta64(1, "D")
    valid &= lag_days <= tolerance
    indices = np.where(valid)[0]
    good_prices = (
        np.isfinite(price_values[indices])
        & np.isfinite(price_values[positions[indices]])
        & (price_values[indices] > 0)
        & (price_values[positions[indices]] > 0)
    )
    indices = indices[good_prices]
    output[indices] = np.log(price_values[indices] / price_values[positions[indices]])
    return pd.Series(output, index=dates.index)


def ewma_vol_by_segment(frame: pd.DataFrame, returns: str, lam: float = 0.94) -> pd.Series:
    output = pd.Series(np.nan, index=frame.index, dtype=float)
    for _, group in frame.groupby("continuous_segment", sort=False):
        values = group[returns].to_numpy(float)
        result = np.full(len(values), np.nan)
        variance = np.nan
        for i in range(1, len(values)):
            prior = values[i - 1]
            if not np.isfinite(prior):
                continue
            if not np.isfinite(variance):
                history = values[max(0, i - 30) : i]
                history = history[np.isfinite(history)]
                variance = float(np.var(history, ddof=1)) if len(history) >= 5 else float(prior**2)
            else:
                variance = lam * variance + (1.0 - lam) * float(prior**2)
            result[i] = math.sqrt(max(variance, 0.0))
        output.loc[group.index] = result
    return output


def load_mandi() -> pd.DataFrame:
    path = INPUTS / "mandi_master.csv"
    frame = pd.read_csv(path)
    frame["date"] = pd.to_datetime(frame["Date"], errors="coerce")
    numeric = [
        "14ANI", "12ANI", "10ANI", "8ANI", "6ANI", "4ANI",
        "5kg", "2kg", "1kgr", "Att", "Melt", "8ANI d/d",
    ]
    for column in numeric:
        frame[column] = as_float(frame[column])
    frame = frame[frame["date"].notna()].sort_values("date").drop_duplicates("date").reset_index(drop=True)
    frame["gap_days"] = frame["date"].diff().dt.days
    frame["continuous_segment"] = frame["gap_days"].gt(14).cumsum().astype(int)

    for column in ["1kgr", "Att", "Melt"]:
        observed = frame["date"].where(frame[column].notna()).ffill()
        frame[f"{column}_age"] = (frame["date"] - observed).dt.days
        frame[f"{column}_filled"] = frame[column].ffill().where(frame[f"{column}_age"] <= 7)

    frame["plate_avg"] = frame[["14ANI", "12ANI", "10ANI", "8ANI", "6ANI"]].mean(axis=1)
    frame["melt_avg"] = frame[["1kgr_filled", "Att_filled", "Melt_filled"]].mean(axis=1)
    frame["plate_melt"] = frame["plate_avg"] - frame["melt_avg"]
    frame["plate_melt_z60"] = rolling_z_by_segment(frame, "plate_melt", 60)
    frame["own_mom_10d"] = calendar_log_change(frame["date"], frame["8ANI"], 10)
    frame["ret_1q"] = np.log(frame["8ANI"]).groupby(frame["continuous_segment"]).diff()
    frame["ewma_vol"] = ewma_vol_by_segment(frame, "ret_1q")

    unchanged = frame["8ANI"].groupby(frame["continuous_segment"]).diff().eq(0).astype(float)
    frame["unchanged_20"] = (
        unchanged.groupby(frame["continuous_segment"])
        .transform(lambda values: values.shift(1).rolling(20, min_periods=10).mean())
    )
    return frame


def load_turkey_nearby() -> tuple[pd.DataFrame, dict]:
    path = INPUTS / "turkey_scrap_daily_nearby.csv"
    frame = pd.read_csv(path)
    frame["date"] = pd.to_datetime(frame["Time"], errors="coerce")
    frame = frame[frame["date"].notna()].copy()
    for column in ["Open", "High", "Low", "Latest", "Change", "Volume", "Open Int"]:
        frame[column] = as_float(frame[column])
    frame = frame.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    frame["roll"] = frame["Symbol"].ne(frame["Symbol"].shift())

    # Change equals the cross-contract nearby gap on rolls in this export, not a
    # same-contract return. Primary returns are missing at every roll and all
    # momentum/volatility windows are calculated strictly within Symbol.
    frame["roll_adjusted_return"] = frame.groupby("Symbol", sort=False)["Latest"].transform(
        lambda values: np.log(values / values.shift(1))
    )
    frame["roll_adjusted_log_index"] = frame["roll_adjusted_return"].fillna(0.0).cumsum()
    frame["roll_adjusted_index"] = 100.0 * np.exp(frame["roll_adjusted_log_index"])

    for lag in [5, 10]:
        frame[f"turkey_mom{lag}"] = frame.groupby("Symbol", sort=False)["Latest"].transform(
            lambda values: np.log(values / values.shift(lag))
        )
    frame["turkey_rv10"] = frame.groupby("Symbol", sort=False)["roll_adjusted_return"].transform(
        lambda values: values.shift(1).rolling(10, min_periods=7).std(ddof=1)
    )
    frame["turkey_zero_range20"] = (
        frame["High"].eq(frame["Low"]).astype(float).shift(1).rolling(20, min_periods=15).mean()
    )
    frame["turkey_zero_oi20"] = (
        frame["Open Int"].le(0).astype(float).shift(1).rolling(20, min_periods=15).mean()
    )

    roll_rows = frame["roll"] & frame.index.to_series().gt(0)
    raw_difference = frame["Latest"].diff()
    audit = {
        "rows": int(len(frame)),
        "first": str(frame["date"].min().date()),
        "last": str(frame["date"].max().date()),
        "contracts": int(frame["Symbol"].nunique()),
        "rolls": int(roll_rows.sum()),
        "duplicate_dates_removed": int(pd.read_csv(path)["Time"].duplicated().sum()),
        "zero_volume_rate": float(frame["Volume"].eq(0).mean()),
        "zero_oi_rate": float(frame["Open Int"].le(0).mean()),
        "zero_range_rate": float(frame["High"].eq(frame["Low"]).mean()),
        "roll_change_missing": int(frame.loc[roll_rows, "Change"].isna().sum()),
        "roll_change_vs_raw_diff_max_abs": float(
            (raw_difference.loc[roll_rows] - frame.loc[roll_rows, "Change"]).abs().max()
        ),
        "roll_return_formula": (
            "missing on Symbol changes; within-Symbol log(Latest_t / Latest_t-1) otherwise. "
            "Change is retained only for the audit because it equals the cross-contract gap on rolls."
        ),
    }
    return frame, audit


def load_bhavnagar() -> tuple[pd.DataFrame, dict]:
    path = INPUTS / "bhavnagar_Bhavnagar_Prices.csv"
    frame = pd.read_csv(path, skiprows=4)
    frame.columns = ["excel_date", "local_tmt", "local_ingot", "local_billet"]
    for column in frame.columns:
        frame[column] = as_float(frame[column])
    frame["date"] = pd.Timestamp("1899-12-30") + pd.to_timedelta(frame["excel_date"], unit="D")
    frame = frame[frame[["local_tmt", "local_ingot", "local_billet"]].notna().any(axis=1)].copy()
    frame = frame.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    frame[["local_tmt", "local_ingot", "local_billet"]] = frame[
        ["local_tmt", "local_ingot", "local_billet"]
    ].ffill(limit=1)
    frame = frame[frame[["local_tmt", "local_ingot", "local_billet"]].notna().all(axis=1)].copy()
    frame["local_tmt_mom10"] = np.log(frame["local_tmt"] / frame["local_tmt"].shift(10))
    frame["local_ingot_mom10"] = np.log(frame["local_ingot"] / frame["local_ingot"].shift(10))
    frame["local_billet_mom10"] = np.log(frame["local_billet"] / frame["local_billet"].shift(10))
    audit = {
        "rows_with_all_prices": int(len(frame)),
        "first": str(frame["date"].min().date()),
        "last": str(frame["date"].max().date()),
        "excel_epoch": "1899-12-30",
        "raw_nonmissing": {
            "tmt": int(pd.read_csv(path, skiprows=4).iloc[:, 1].notna().sum()),
            "ingot": int(pd.read_csv(path, skiprows=4).iloc[:, 2].notna().sum()),
            "billet": int(pd.read_csv(path, skiprows=4).iloc[:, 3].notna().sum()),
        },
    }
    return frame, audit


def strict_prior_asof(
    left: pd.DataFrame,
    right: pd.DataFrame,
    right_date_name: str,
    columns: Iterable[str],
) -> pd.DataFrame:
    right_columns = ["date", *columns]
    renamed = right[right_columns].rename(columns={"date": right_date_name})
    merged = pd.merge_asof(
        left.sort_values("date"),
        renamed.sort_values(right_date_name),
        left_on="date",
        right_on=right_date_name,
        direction="backward",
        allow_exact_matches=False,
    )
    return merged


def build_panel() -> tuple[pd.DataFrame, dict]:
    mandi = load_mandi()
    turkey, turkey_audit = load_turkey_nearby()
    local, local_audit = load_bhavnagar()

    turkey_columns = [
        "Symbol", "Latest", "Volume", "Open Int", "roll", "roll_adjusted_return",
        "roll_adjusted_index", "turkey_mom5", "turkey_mom10", "turkey_rv10",
        "turkey_zero_range20", "turkey_zero_oi20",
    ]
    panel = strict_prior_asof(mandi, turkey, "turkey_date", turkey_columns)
    panel["turkey_age"] = (panel["date"] - panel["turkey_date"]).dt.days
    panel["turkey_stale"] = panel["turkey_age"].gt(MAX_STALENESS_DAYS)
    panel["turkey_quality"] = (
        panel["turkey_age"].le(MAX_STALENESS_DAYS)
        & panel["Open Int"].gt(0)
        & panel["Latest"].gt(0)
    )

    local_columns = [
        "local_tmt", "local_ingot", "local_billet",
        "local_tmt_mom10", "local_ingot_mom10", "local_billet_mom10",
    ]
    panel = strict_prior_asof(panel, local, "local_date", local_columns)
    panel["local_age"] = (panel["date"] - panel["local_date"]).dt.days
    panel["local_stale"] = panel["local_age"].gt(MAX_STALENESS_DAYS)
    panel["local_quality"] = (
        panel["local_age"].le(MAX_STALENESS_DAYS)
        & panel[["local_tmt", "local_ingot", "local_billet"]].notna().all(axis=1)
    )

    panel["scrap_ingot_log_basis"] = np.log(panel["8ANI"] / panel["local_ingot"])
    panel["scrap_ingot_z60"] = rolling_z_by_segment(panel, "scrap_ingot_log_basis", 60)
    panel["common_feature_quality"] = (
        panel["turkey_quality"]
        & panel["local_quality"]
        & panel[COMBINED_FEATURES].notna().all(axis=1)
    )

    assert (panel.loc[panel["turkey_date"].notna(), "turkey_date"] < panel.loc[
        panel["turkey_date"].notna(), "date"
    ]).all(), "Turkey join is not strictly prior-date"
    assert (panel.loc[panel["local_date"].notna(), "local_date"] < panel.loc[
        panel["local_date"].notna(), "date"
    ]).all(), "Bhavnagar join is not strictly prior-date"

    audit = {
        "mandi": {
            "rows": int(len(mandi)),
            "first": str(mandi["date"].min().date()),
            "last": str(mandi["date"].max().date()),
            "large_gaps_over_14d": mandi.loc[mandi["gap_days"] > 14, "gap_days"].astype(int).tolist(),
            "segments": int(mandi["continuous_segment"].nunique()),
        },
        "turkey": turkey_audit,
        "bhavnagar": local_audit,
        "joins": {
            "strict_prior_turkey_matches": int(panel["turkey_date"].notna().sum()),
            "turkey_under_4d_and_positive_oi": int(panel["turkey_quality"].sum()),
            "strict_prior_local_matches": int(panel["local_date"].notna().sum()),
            "local_under_4d": int(panel["local_quality"].sum()),
            "common_feature_quality_rows": int(panel["common_feature_quality"].sum()),
            "max_turkey_date_violation": 0,
            "max_local_date_violation": 0,
        },
    }
    return panel, audit


def add_targets(panel: pd.DataFrame) -> pd.DataFrame:
    dates = panel["date"].to_numpy(dtype="datetime64[ns]")
    prices = panel["8ANI"].to_numpy(float)
    for horizon in HORIZONS:
        endpoints = np.searchsorted(dates, dates + np.timedelta64(horizon, "D"), side="left")
        endpoint_dates = np.full(len(panel), np.datetime64("NaT"), dtype="datetime64[ns]")
        endpoint_prices = np.full(len(panel), np.nan)
        rows = np.where(endpoints < len(panel))[0]
        endpoint_dates[rows] = dates[endpoints[rows]]
        endpoint_prices[rows] = prices[endpoints[rows]]
        elapsed = (endpoint_dates - dates) / np.timedelta64(1, "D")
        valid = (elapsed >= horizon) & (elapsed <= horizon + TARGET_TOLERANCE_DAYS)
        panel[f"target_end_{horizon}"] = pd.Series(endpoint_dates).where(valid)
        panel[f"target_ret_{horizon}"] = np.where(valid, np.log(endpoint_prices / prices), np.nan)
        panel[f"target_change_{horizon}"] = np.where(valid, endpoint_prices - prices, np.nan)
        panel[f"target_dir_{horizon}"] = np.where(
            valid,
            np.where(endpoint_prices > prices, 1, np.where(endpoint_prices < prices, -1, 0)),
            np.nan,
        )
        valid_rows = panel[f"target_end_{horizon}"].notna()
        actual_elapsed = (
            panel.loc[valid_rows, f"target_end_{horizon}"] - panel.loc[valid_rows, "date"]
        ).dt.days
        assert actual_elapsed.between(horizon, horizon + TARGET_TOLERANCE_DAYS).all()
    return panel


@dataclass
class Preprocessor:
    median: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    mean: np.ndarray
    scale: np.ndarray


def fit_preprocessor(values: np.ndarray) -> Preprocessor:
    median = np.nanmedian(values, axis=0)
    median = np.where(np.isfinite(median), median, 0.0)
    imputed = np.where(np.isfinite(values), values, median)
    lower = np.nanpercentile(imputed, 1, axis=0)
    upper = np.nanpercentile(imputed, 99, axis=0)
    clipped = np.clip(imputed, lower, upper)
    mean = clipped.mean(axis=0)
    scale = clipped.std(axis=0, ddof=1)
    scale = np.where(np.isfinite(scale) & (scale > 1e-10), scale, 1.0)
    return Preprocessor(median, lower, upper, mean, scale)


def apply_preprocessor(values: np.ndarray, processor: Preprocessor) -> np.ndarray:
    imputed = np.where(np.isfinite(values), values, processor.median)
    clipped = np.clip(imputed, processor.lower, processor.upper)
    return (clipped - processor.mean) / processor.scale


def augment_nonlinear(values: np.ndarray, feature_names: list[str]) -> np.ndarray:
    positions = {name: i for i, name in enumerate(feature_names)}
    plate = values[:, positions["plate_melt_z60"]]
    basis = values[:, positions["scrap_ingot_z60"]]
    turkey10 = values[:, positions["turkey_mom10"]]
    ingot10 = values[:, positions["local_ingot_mom10"]]
    extras = np.column_stack([
        np.maximum(plate - 1.0, 0.0),
        np.maximum(-plate - 1.0, 0.0),
        np.maximum(basis - 1.0, 0.0),
        np.maximum(-basis - 1.0, 0.0),
        np.clip(turkey10 * ingot10, -6.0, 6.0),
    ])
    return np.column_stack([values, extras])


def prepare_xy(
    panel: pd.DataFrame,
    indices: np.ndarray,
    model: str,
    processor: Preprocessor | None = None,
) -> tuple[np.ndarray, Preprocessor]:
    names = MODEL_FEATURES[model]
    raw = panel.loc[indices, names].to_numpy(float)
    if processor is None:
        processor = fit_preprocessor(raw)
    standardized = apply_preprocessor(raw, processor)
    if model == "nonlinear":
        standardized = augment_nonlinear(standardized, names)
    return standardized, processor


def ridge_fit(values: np.ndarray, target: np.ndarray, alpha: float) -> np.ndarray:
    design = np.column_stack([np.ones(len(values)), values])
    penalty = np.eye(design.shape[1]) * alpha
    penalty[0, 0] = 0.0
    return np.linalg.pinv(design.T @ design + penalty) @ (design.T @ target)


def ridge_predict(beta: np.ndarray, values: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(values)), values]) @ beta


def labels_to_indices(labels: np.ndarray) -> np.ndarray:
    return np.searchsorted(CLASSES, labels.astype(int))


def one_hot(labels: np.ndarray) -> np.ndarray:
    output = np.zeros((len(labels), len(CLASSES)), dtype=float)
    output[np.arange(len(labels)), labels_to_indices(labels)] = 1.0
    return output


def class_probabilities(raw: np.ndarray, class_frequency: np.ndarray) -> np.ndarray:
    clipped = np.clip(raw, 0.0, None)
    clipped += 0.15 * class_frequency.reshape(1, -1)
    denominator = clipped.sum(axis=1, keepdims=True)
    bad = denominator[:, 0] <= 0
    clipped[bad] = class_frequency
    return clipped / clipped.sum(axis=1, keepdims=True)


def fit_heads(
    x: np.ndarray,
    y_magnitude: np.ndarray,
    y_class: np.ndarray,
    alpha_magnitude: float,
    alpha_class: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    beta_magnitude = ridge_fit(x, y_magnitude, alpha_magnitude)
    beta_class = ridge_fit(x, one_hot(y_class), alpha_class)
    counts = np.array([(y_class == value).sum() for value in CLASSES], dtype=float)
    class_frequency = (counts + 1.0) / (len(y_class) + len(CLASSES))
    return beta_magnitude, beta_class, class_frequency


def predict_heads(
    x: np.ndarray,
    beta_magnitude: np.ndarray,
    beta_class: np.ndarray,
    class_frequency: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    magnitude = ridge_predict(beta_magnitude, x)
    raw_class = ridge_predict(beta_class, x)
    return magnitude, class_probabilities(raw_class, class_frequency)


def brier_loss(y_class: np.ndarray, probabilities: np.ndarray) -> np.ndarray:
    return np.sum((one_hot(y_class) - probabilities) ** 2, axis=1)


def log_loss(y_class: np.ndarray, probabilities: np.ndarray) -> np.ndarray:
    indices = labels_to_indices(y_class)
    selected = probabilities[np.arange(len(probabilities)), indices]
    return -np.log(np.clip(selected, 1e-12, 1.0))


def choose_alphas(
    panel: pd.DataFrame,
    train_indices: np.ndarray,
    model: str,
    horizon: int,
) -> tuple[float, float]:
    if model == "baseline":
        return np.nan, np.nan
    target = f"target_ret_{horizon}"
    target_class = f"target_dir_{horizon}"
    target_end = f"target_end_{horizon}"
    ordered = np.array(sorted(train_indices, key=lambda idx: panel.at[idx, "date"]))
    boundaries = [0.55, 0.70, 0.85, 1.0]
    magnitude_scores = {alpha: [] for alpha in ALPHAS}
    class_scores = {alpha: [] for alpha in ALPHAS}

    for fold in range(3):
        start = int(len(ordered) * boundaries[fold])
        stop = int(len(ordered) * boundaries[fold + 1])
        validation = ordered[start:stop]
        if len(validation) < 10:
            continue
        validation_start = panel.at[validation[0], "date"]
        inner_train = ordered[panel.loc[ordered, target_end].to_numpy() < np.datetime64(validation_start)]
        if len(inner_train) < 60:
            continue
        x_train, processor = prepare_xy(panel, inner_train, model)
        x_validation, _ = prepare_xy(panel, validation, model, processor)
        y_train = panel.loc[inner_train, target].to_numpy(float)
        c_train = panel.loc[inner_train, target_class].to_numpy(int)
        y_validation = panel.loc[validation, target].to_numpy(float)
        c_validation = panel.loc[validation, target_class].to_numpy(int)
        counts = np.array([(c_train == value).sum() for value in CLASSES], dtype=float)
        frequency = (counts + 1.0) / (len(c_train) + len(CLASSES))
        for alpha in ALPHAS:
            magnitude_beta = ridge_fit(x_train, y_train, alpha)
            magnitude_prediction = ridge_predict(magnitude_beta, x_validation)
            magnitude_scores[alpha].extend(np.abs(y_validation - magnitude_prediction).tolist())

            class_beta = ridge_fit(x_train, one_hot(c_train), alpha)
            probabilities = class_probabilities(ridge_predict(class_beta, x_validation), frequency)
            class_scores[alpha].extend(brier_loss(c_validation, probabilities).tolist())

    def select(scores: dict[float, list[float]], default: float = 10.0) -> float:
        available = [(float(np.mean(losses)), alpha) for alpha, losses in scores.items() if losses]
        if not available:
            return default
        best_loss = min(item[0] for item in available)
        # One-percent simplicity band: prefer stronger shrinkage when losses are practically tied.
        eligible = [alpha for loss, alpha in available if loss <= best_loss * 1.01 + 1e-12]
        return float(max(eligible))

    return select(magnitude_scores), select(class_scores)


def greedy_nonoverlap(frame: pd.DataFrame) -> pd.DataFrame:
    selected: list[int] = []
    last_end = pd.Timestamp.min
    for index, row in frame.sort_values("origin_date").iterrows():
        if row["origin_date"] >= last_end:
            selected.append(index)
            last_end = row["target_end"]
    return frame.loc[selected].copy()


def common_origins(panel: pd.DataFrame, horizon: int) -> np.ndarray:
    target = f"target_ret_{horizon}"
    target_end = f"target_end_{horizon}"
    eligible = panel["common_feature_quality"] & panel[target].notna() & panel[target_end].notna()
    origins = []
    last_kept: pd.Timestamp | None = None
    for index in panel.index[eligible]:
        origin_date = panel.at[index, "date"]
        matured = eligible & (panel[target_end] < origin_date)
        if (
            int(matured.sum()) >= MIN_RAW_TRAIN
            and (last_kept is None or (origin_date - last_kept).days >= OOS_ORIGIN_SPACING_DAYS)
        ):
            origins.append(index)
            last_kept = origin_date
    # Preserve the latest mature label as an audit origin when it is not already present.
    eligible_indices = panel.index[eligible].to_numpy(dtype=int)
    if len(eligible_indices):
        latest = int(eligible_indices[-1])
        latest_date = panel.at[latest, "date"]
        matured = eligible & (panel[target_end] < latest_date)
        if int(matured.sum()) >= MIN_RAW_TRAIN and (not origins or origins[-1] != latest):
            origins.append(latest)
    return np.array(origins, dtype=int)


def train_nonoverlap_count(panel: pd.DataFrame, indices: np.ndarray, horizon: int) -> int:
    origins = panel.loc[indices, "date"].to_numpy(dtype="datetime64[ns]")
    ends = panel.loc[indices, f"target_end_{horizon}"].to_numpy(dtype="datetime64[ns]")
    count = 0
    last_end = np.datetime64("1900-01-01")
    for origin, end in zip(origins, ends):
        if origin >= last_end:
            count += 1
            last_end = end
    return count


def backtest_model(
    panel: pd.DataFrame,
    horizon: int,
    model: str,
    origins: np.ndarray,
) -> pd.DataFrame:
    target = f"target_ret_{horizon}"
    target_change = f"target_change_{horizon}"
    target_class = f"target_dir_{horizon}"
    target_end = f"target_end_{horizon}"
    eligible_train = panel["common_feature_quality"] & panel[target].notna() & panel[target_end].notna()
    alpha_cache: dict[str, tuple[float, float]] = {}
    rows: list[dict] = []

    for origin in origins:
        origin_date = panel.at[origin, "date"]
        matured = eligible_train & (panel[target_end] < origin_date)
        train_indices = panel.index[matured].to_numpy(dtype=int)
        assert len(train_indices) >= MIN_RAW_TRAIN
        assert (panel.loc[train_indices, target_end] < origin_date).all(), "Purging failure"

        y_train = panel.loc[train_indices, target].to_numpy(float)
        c_train = panel.loc[train_indices, target_class].to_numpy(int)
        counts = np.array([(c_train == value).sum() for value in CLASSES], dtype=float)
        frequency = (counts + 1.0) / (len(c_train) + len(CLASSES))
        median_baseline = float(np.median(y_train[-min(120, len(y_train)) :]))

        if model == "baseline":
            magnitude_prediction = 0.0
            probabilities = frequency
            interval_half = float(np.quantile(np.abs(y_train), 0.80))
            alpha_magnitude = np.nan
            alpha_class = np.nan
        else:
            cache_key = str(origin_date.to_period("M"))
            if cache_key not in alpha_cache:
                alpha_cache[cache_key] = choose_alphas(panel, train_indices, model, horizon)
            alpha_magnitude, alpha_class = alpha_cache[cache_key]
            x_train, processor = prepare_xy(panel, train_indices, model)
            x_test, _ = prepare_xy(panel, np.array([origin]), model, processor)
            beta_magnitude, beta_class, fitted_frequency = fit_heads(
                x_train, y_train, c_train, alpha_magnitude, alpha_class
            )
            predicted_magnitude, predicted_probability = predict_heads(
                x_test, beta_magnitude, beta_class, fitted_frequency
            )
            magnitude_prediction = float(predicted_magnitude[0])
            probabilities = predicted_probability[0]
            residuals = y_train - ridge_predict(beta_magnitude, x_train)
            inflation = math.sqrt(1.0 + x_train.shape[1] / max(len(x_train), 1))
            interval_half = float(np.quantile(np.abs(residuals), 0.80) * inflation)

        predicted_class = int(CLASSES[int(np.argmax(probabilities))])
        current_price = float(panel.at[origin, "8ANI"])
        rows.append({
            "model": model,
            "horizon": horizon,
            "origin_index": int(origin),
            "origin_date": origin_date,
            "target_end": panel.at[origin, target_end],
            "current_price": current_price,
            "actual_log_return": float(panel.at[origin, target]),
            "actual_change_rupee": float(panel.at[origin, target_change]),
            "actual_class": int(panel.at[origin, target_class]),
            "predicted_log_return": magnitude_prediction,
            "zero_baseline_log_return": 0.0,
            "median_baseline_log_return": median_baseline,
            "prob_down": float(probabilities[0]),
            "prob_flat": float(probabilities[1]),
            "prob_up": float(probabilities[2]),
            "predicted_class": predicted_class,
            "freq_prob_down": float(frequency[0]),
            "freq_prob_flat": float(frequency[1]),
            "freq_prob_up": float(frequency[2]),
            "majority_class": int(CLASSES[int(np.argmax(frequency))]),
            "lower80_log_return": magnitude_prediction - interval_half,
            "upper80_log_return": magnitude_prediction + interval_half,
            "interval_half80": interval_half,
            "alpha_magnitude": alpha_magnitude,
            "alpha_class": alpha_class,
            "train_raw_n": int(len(train_indices)),
            "train_nonoverlap_n": train_nonoverlap_count(panel, train_indices, horizon),
            "turkey_date": panel.at[origin, "turkey_date"],
            "turkey_age": float(panel.at[origin, "turkey_age"]),
            "turkey_symbol": panel.at[origin, "Symbol"],
            "turkey_open_interest": float(panel.at[origin, "Open Int"]),
            "local_date": panel.at[origin, "local_date"],
            "local_age": float(panel.at[origin, "local_age"]),
        })

    return pd.DataFrame(rows)


def add_point_in_time_calls(predictions: pd.DataFrame) -> pd.DataFrame:
    output_parts = []
    for (horizon, model), group in predictions.groupby(["horizon", "model"], sort=False):
        group = group.sort_values("origin_date").copy()
        calls: list[str] = []
        reasons: list[str] = []
        past_skill_values: list[float] = []
        past_nonoverlap_values: list[int] = []
        for position, (_, row) in enumerate(group.iterrows()):
            past = group.iloc[:position]
            past_nonoverlap = greedy_nonoverlap(past) if len(past) else past
            past_n = int(len(past_nonoverlap))
            past_skill = (
                float(np.mean(np.abs(past["actual_log_return"])) - np.mean(
                    np.abs(past["actual_log_return"] - past["predicted_log_return"])
                ))
                if len(past) else np.nan
            )
            past_skill_values.append(past_skill)
            past_nonoverlap_values.append(past_n)
            if model == "baseline":
                calls.append("NO CALL")
                reasons.append("baseline model")
                continue
            row_reasons = []
            if past_n < 20:
                row_reasons.append("past independent N<20")
            if not np.isfinite(past_skill) or past_skill <= 0:
                row_reasons.append("past MAE skill<=0")
            class_probability = max(row["prob_down"], row["prob_flat"], row["prob_up"])
            if class_probability < 0.50:
                row_reasons.append("class confidence<0.50")
            holding_hurdle_rupee = 30.0 * horizon
            up_hurdle = math.log(
                (row["current_price"] + holding_hurdle_rupee) / row["current_price"]
            )
            down_hurdle = abs(math.log((row["current_price"] - 100.0) / row["current_price"]))
            proposed = "NO CALL"
            if (
                row["lower80_log_return"] > up_hurdle
                and row["predicted_class"] == 1
            ):
                proposed = "UP / HOLD"
            elif (
                row["upper80_log_return"] < -down_hurdle
                and row["predicted_class"] == -1
            ):
                proposed = "DOWN / SELL"
            else:
                row_reasons.append(
                    f"80% interval/class does not clear holding hurdle Rs{holding_hurdle_rupee:.0f}"
                )
            if row_reasons:
                calls.append("NO CALL")
                reasons.append("; ".join(row_reasons))
            else:
                calls.append(proposed)
                reasons.append("all point-in-time gates passed")
        group["past_oos_mae_skill_zero"] = past_skill_values
        group["past_nonoverlap_n"] = past_nonoverlap_values
        group["operational_call_pti"] = calls
        group["operational_call_reason_pti"] = reasons
        output_parts.append(group)
    return pd.concat(output_parts, ignore_index=True)


def block_length(frame: pd.DataFrame, horizon: int) -> int:
    spacing = frame["origin_date"].sort_values().diff().dt.days.dropna()
    median_spacing = float(spacing.median()) if len(spacing) else 1.0
    proposed = max(3, int(round(horizon / max(median_spacing, 1.0))))
    return min(proposed, max(3, len(frame) // 3))


def circular_block_indices(n: int, block: int, rng: np.random.Generator) -> np.ndarray:
    indices: list[int] = []
    while len(indices) < n:
        start = int(rng.integers(0, n))
        indices.extend(((start + np.arange(block)) % n).tolist())
    return np.asarray(indices[:n], dtype=int)


def moving_block_ci(values: np.ndarray, block: int, reps: int = BOOTSTRAP_REPS) -> tuple[float, float, float]:
    values = np.asarray(values, dtype=float)
    if len(values) < 5:
        return np.nan, np.nan, np.nan
    means = np.empty(reps)
    for rep in range(reps):
        indices = circular_block_indices(len(values), block, RNG)
        means[rep] = float(np.mean(values[indices]))
    return (
        float(np.quantile(means, 0.025)),
        float(np.quantile(means, 0.975)),
        float(np.std(means, ddof=1)),
    )


def confusion_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict:
    matrix = np.zeros((3, 3), dtype=int)
    actual_index = labels_to_indices(actual)
    predicted_index = labels_to_indices(predicted)
    for true_value, predicted_value in zip(actual_index, predicted_index):
        matrix[true_value, predicted_value] += 1
    recalls = []
    precisions = []
    f1_values = []
    for index in range(3):
        tp = matrix[index, index]
        recall = tp / matrix[index].sum() if matrix[index].sum() else np.nan
        precision = tp / matrix[:, index].sum() if matrix[:, index].sum() else np.nan
        f1 = 2 * precision * recall / (precision + recall) if precision + recall > 0 else np.nan
        recalls.append(recall)
        precisions.append(precision)
        f1_values.append(f1)

    n = matrix.sum()
    correct = np.trace(matrix)
    row_sum = matrix.sum(axis=1)
    col_sum = matrix.sum(axis=0)
    numerator = correct * n - np.dot(row_sum, col_sum)
    denominator = math.sqrt(
        max((n**2 - np.dot(col_sum, col_sum)) * (n**2 - np.dot(row_sum, row_sum)), 0.0)
    )
    mcc = numerator / denominator if denominator else np.nan
    return {
        "accuracy": float(correct / n) if n else np.nan,
        "balanced_accuracy": float(np.nanmean(recalls)),
        "macro_f1": float(np.nanmean(f1_values)),
        "mcc": float(mcc),
        "down_precision": float(precisions[0]),
        "flat_precision": float(precisions[1]),
        "up_precision": float(precisions[2]),
        "down_recall": float(recalls[0]),
        "flat_recall": float(recalls[1]),
        "up_recall": float(recalls[2]),
        "confusion_json": json.dumps(matrix.tolist()),
    }


def phase_offset_stability(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (horizon, model), group in predictions.groupby(["horizon", "model"], sort=False):
        anchor = pd.Timestamp("2000-01-01")
        group = group.copy()
        group["phase_offset"] = ((group["origin_date"] - anchor).dt.days % horizon).astype(int)
        for phase, phase_group in group.groupby("phase_offset"):
            independent = greedy_nonoverlap(phase_group)
            if independent.empty:
                continue
            actual = independent["actual_log_return"].to_numpy(float)
            predicted = independent["predicted_log_return"].to_numpy(float)
            classes = independent["actual_class"].to_numpy(int)
            probabilities = independent[["prob_down", "prob_flat", "prob_up"]].to_numpy(float)
            frequency = independent[["freq_prob_down", "freq_prob_flat", "freq_prob_up"]].to_numpy(float)
            rows.append({
                "horizon": horizon,
                "model": model,
                "phase_offset": int(phase),
                "n": int(len(independent)),
                "mae_skill_zero": float(np.mean(np.abs(actual)) - np.mean(np.abs(actual - predicted))),
                "brier_skill_frequency": float(
                    np.mean(brier_loss(classes, frequency)) - np.mean(brier_loss(classes, probabilities))
                ),
                "direction_accuracy": float((independent["predicted_class"] == independent["actual_class"]).mean()),
            })
    return pd.DataFrame(rows)


def summarize_predictions(predictions: pd.DataFrame, phases: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (horizon, model), group in predictions.groupby(["horizon", "model"], sort=False):
        group = group.sort_values("origin_date")
        independent = greedy_nonoverlap(group)
        actual = group["actual_log_return"].to_numpy(float)
        predicted = group["predicted_log_return"].to_numpy(float)
        median_baseline = group["median_baseline_log_return"].to_numpy(float)
        classes = group["actual_class"].to_numpy(int)
        probabilities = group[["prob_down", "prob_flat", "prob_up"]].to_numpy(float)
        frequency = group[["freq_prob_down", "freq_prob_flat", "freq_prob_up"]].to_numpy(float)
        predicted_classes = group["predicted_class"].to_numpy(int)
        majority_classes = group["majority_class"].to_numpy(int)

        absolute_error = np.abs(actual - predicted)
        zero_error = np.abs(actual)
        median_error = np.abs(actual - median_baseline)
        mae_diff = zero_error - absolute_error
        brier_model = brier_loss(classes, probabilities)
        brier_frequency = brier_loss(classes, frequency)
        brier_diff = brier_frequency - brier_model
        block = block_length(group, horizon)
        mae_low, mae_high, mae_se = moving_block_ci(mae_diff, block)
        brier_low, brier_high, brier_se = moving_block_ci(brier_diff, block)

        thirds = np.array_split(np.arange(len(group)), 3)
        third_skills = [float(np.mean(mae_diff[index])) for index in thirds if len(index)]
        phase_group = phases[(phases["horizon"] == horizon) & (phases["model"] == model)]
        usable_phases = phase_group[phase_group["n"] >= 2]

        calls = group[group["operational_call_pti"] != "NO CALL"]
        call_sign = calls["operational_call_pti"].map({"UP / HOLD": 1, "DOWN / SELL": -1}).to_numpy(float)
        call_hit = (
            float((call_sign == np.sign(calls["actual_log_return"].to_numpy(float))).mean())
            if len(calls) else np.nan
        )
        call_signed_rupee = (
            float(np.mean(call_sign * calls["actual_change_rupee"].to_numpy(float)))
            if len(calls) else np.nan
        )

        metrics = confusion_metrics(classes, predicted_classes)
        majority_metrics = confusion_metrics(classes, majority_classes)
        rows.append({
            "horizon": horizon,
            "model": model,
            "raw_oos_n": int(len(group)),
            "nonoverlap_n": int(len(independent)),
            "first_oos_origin": str(group["origin_date"].min().date()),
            "last_oos_origin": str(group["origin_date"].max().date()),
            "mae_log": float(np.mean(absolute_error)),
            "zero_mae_log": float(np.mean(zero_error)),
            "median_baseline_mae_log": float(np.mean(median_error)),
            "mae_skill_zero_log": float(np.mean(mae_diff)),
            "mae_skill_zero_pct": float(np.mean(mae_diff) / np.mean(zero_error)) if np.mean(zero_error) else np.nan,
            "mae_skill_zero_ci_low": mae_low,
            "mae_skill_zero_ci_high": mae_high,
            "mae_skill_zero_boot_se": mae_se,
            "median_ae_log": float(np.median(absolute_error)),
            "rmse_log": float(math.sqrt(np.mean((actual - predicted) ** 2))),
            "oos_r2_vs_zero": float(1.0 - np.sum((actual - predicted) ** 2) / np.sum(actual**2)) if np.sum(actual**2) else np.nan,
            "nonoverlap_mae_skill_zero_log": float(
                np.mean(np.abs(independent["actual_log_return"]))
                - np.mean(np.abs(independent["actual_log_return"] - independent["predicted_log_return"]))
            ),
            "brier": float(np.mean(brier_model)),
            "frequency_brier": float(np.mean(brier_frequency)),
            "brier_skill_frequency": float(np.mean(brier_diff)),
            "brier_skill_frequency_ci_low": brier_low,
            "brier_skill_frequency_ci_high": brier_high,
            "brier_skill_frequency_boot_se": brier_se,
            "log_loss": float(np.mean(log_loss(classes, probabilities))),
            "frequency_log_loss": float(np.mean(log_loss(classes, frequency))),
            "accuracy": metrics["accuracy"],
            "majority_accuracy": majority_metrics["accuracy"],
            "accuracy_edge_majority": metrics["accuracy"] - majority_metrics["accuracy"],
            "balanced_accuracy": metrics["balanced_accuracy"],
            "macro_f1": metrics["macro_f1"],
            "mcc": metrics["mcc"],
            "down_precision": metrics["down_precision"],
            "flat_precision": metrics["flat_precision"],
            "up_precision": metrics["up_precision"],
            "down_recall": metrics["down_recall"],
            "flat_recall": metrics["flat_recall"],
            "up_recall": metrics["up_recall"],
            "confusion_json": metrics["confusion_json"],
            "time_third_skill_min": float(min(third_skills)),
            "time_third_skill_median": float(np.median(third_skills)),
            "phase_count_n_ge_2": int(len(usable_phases)),
            "phase_skill_median": float(usable_phases["mae_skill_zero"].median()) if len(usable_phases) else np.nan,
            "phase_skill_min": float(usable_phases["mae_skill_zero"].min()) if len(usable_phases) else np.nan,
            "phase_skill_positive_share": float((usable_phases["mae_skill_zero"] > 0).mean()) if len(usable_phases) else np.nan,
            "pti_call_n": int(len(calls)),
            "pti_call_coverage": float(len(calls) / len(group)),
            "pti_call_hit": call_hit,
            "pti_call_mean_signed_rupee": call_signed_rupee,
            "block_length_origins": block,
        })
    return pd.DataFrame(rows)


def pairwise_same_origin(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for horizon, horizon_frame in predictions.groupby("horizon"):
        internal = horizon_frame[horizon_frame["model"] == "internal"].set_index("origin_date")
        for model in [name for name in MODEL_ORDER if name not in {"baseline", "internal"}]:
            candidate = horizon_frame[horizon_frame["model"] == model].set_index("origin_date")
            common = internal.index.intersection(candidate.index)
            assert len(common) == len(internal) == len(candidate), "Models do not share identical origins"
            left = internal.loc[common]
            right = candidate.loc[common]
            actual = left["actual_log_return"].to_numpy(float)
            internal_error = np.abs(actual - left["predicted_log_return"].to_numpy(float))
            candidate_error = np.abs(actual - right["predicted_log_return"].to_numpy(float))
            classes = left["actual_class"].to_numpy(int)
            internal_prob = left[["prob_down", "prob_flat", "prob_up"]].to_numpy(float)
            candidate_prob = right[["prob_down", "prob_flat", "prob_up"]].to_numpy(float)
            rows.append({
                "horizon": int(horizon),
                "candidate": model,
                "reference": "internal",
                "same_origin_n": int(len(common)),
                "candidate_mae_improvement_log": float(np.mean(internal_error - candidate_error)),
                "candidate_brier_improvement": float(
                    np.mean(brier_loss(classes, internal_prob) - brier_loss(classes, candidate_prob))
                ),
            })
    return pd.DataFrame(rows)


def max_null_adjustment(predictions: pd.DataFrame, metric: str) -> tuple[pd.DataFrame, dict]:
    candidates = [model for model in MODEL_ORDER if model != "baseline"]
    matrices: dict[int, dict] = {}
    for horizon in HORIZONS:
        groups = {
            model: predictions[(predictions["horizon"] == horizon) & (predictions["model"] == model)]
            .sort_values("origin_date")
            .reset_index(drop=True)
            for model in candidates
        }
        lengths = {len(frame) for frame in groups.values()}
        assert len(lengths) == 1, "Candidate model origins differ within a horizon"
        reference_dates = groups[candidates[0]]["origin_date"]
        assert all(groups[model]["origin_date"].equals(reference_dates) for model in candidates)
        actual = groups[candidates[0]]["actual_log_return"].to_numpy(float)
        classes = groups[candidates[0]]["actual_class"].to_numpy(int)
        if metric == "mae_skill_zero":
            matrix = np.column_stack([
                np.abs(actual)
                - np.abs(actual - groups[model]["predicted_log_return"].to_numpy(float))
                for model in candidates
            ])
        elif metric == "brier_skill_frequency":
            frequency = groups[candidates[0]][["freq_prob_down", "freq_prob_flat", "freq_prob_up"]].to_numpy(float)
            baseline_loss = brier_loss(classes, frequency)
            matrix = np.column_stack([
                baseline_loss - brier_loss(
                    classes,
                    groups[model][["prob_down", "prob_flat", "prob_up"]].to_numpy(float),
                )
                for model in candidates
            ])
        else:
            raise ValueError(metric)
        frame_for_block = groups[candidates[0]]
        block = block_length(frame_for_block, horizon)
        boot_means = np.empty((MAX_NULL_REPS, len(candidates)))
        for rep in range(MAX_NULL_REPS):
            indices = circular_block_indices(len(matrix), block, RNG)
            boot_means[rep] = matrix[indices].mean(axis=0)
        standard_error = boot_means.std(axis=0, ddof=1)
        standard_error = np.where(standard_error > 1e-12, standard_error, np.inf)
        observed = matrix.mean(axis=0)
        centered_boot = boot_means - observed
        matrices[horizon] = {
            "matrix": matrix,
            "observed": observed,
            "standard_error": standard_error,
            "centered_boot": centered_boot,
            "block": block,
            "n": len(matrix),
        }

    max_null_t = np.empty(MAX_NULL_REPS)
    max_null_raw = np.empty(MAX_NULL_REPS)
    for rep in range(MAX_NULL_REPS):
        t_values = []
        raw_values = []
        for horizon in HORIZONS:
            item = matrices[horizon]
            centered = item["centered_boot"][rep]
            t_values.extend((centered / item["standard_error"]).tolist())
            raw_values.extend(centered.tolist())
        max_null_t[rep] = max(t_values)
        max_null_raw[rep] = max(raw_values)

    null_95_t = float(np.quantile(max_null_t, 0.95))
    null_95_raw = float(np.quantile(max_null_raw, 0.95))
    rows = []
    for horizon in HORIZONS:
        item = matrices[horizon]
        for column, model in enumerate(candidates):
            observed = float(item["observed"][column])
            se = float(item["standard_error"][column])
            t_stat = observed / se if np.isfinite(se) and se > 0 else np.nan
            own_null_t = item["centered_boot"][:, column] / se
            unadjusted = float((1 + np.sum(own_null_t >= t_stat)) / (1 + MAX_NULL_REPS))
            adjusted = float((1 + np.sum(max_null_t >= t_stat)) / (1 + MAX_NULL_REPS))
            rows.append({
                "metric": metric,
                "horizon": horizon,
                "model": model,
                "candidate_id": f"{model}_{horizon}d",
                "observed_skill": observed,
                "block_bootstrap_se": se,
                "studentized_stat": t_stat,
                "unadjusted_p_one_sided": unadjusted,
                "max_null_adjusted_p": adjusted,
                "global_null_95_t": null_95_t,
                "global_null_95_raw_skill": null_95_raw,
                "deflated_skill_vs_global_raw95": observed - null_95_raw,
                "oos_n": item["n"],
                "block_length_origins": item["block"],
            })
    metadata = {
        "metric": metric,
        "candidate_count": len(HORIZONS) * len(candidates),
        "replications": MAX_NULL_REPS,
        "null_95_max_studentized": null_95_t,
        "null_95_max_raw_skill": null_95_raw,
        "method": (
            "Joint within-horizon circular moving-block bootstrap of centered OOS loss "
            "differentials; maximum studentized statistic across 5 pre-specified models x 7 horizons."
        ),
    }
    return pd.DataFrame(rows), metadata


def fit_live_forecasts(
    panel: pd.DataFrame,
    summaries: pd.DataFrame,
    adjustment: pd.DataFrame,
) -> pd.DataFrame:
    live_index = int(panel.index[-1])
    live_date = panel.at[live_index, "date"]
    current_price = float(panel.at[live_index, "8ANI"])
    rows = []
    for horizon in HORIZONS:
        target = f"target_ret_{horizon}"
        target_class = f"target_dir_{horizon}"
        target_end = f"target_end_{horizon}"
        eligible = panel["common_feature_quality"] & panel[target].notna() & panel[target_end].notna()
        train_indices = panel.index[eligible & (panel[target_end] < live_date)].to_numpy(dtype=int)
        train_nonoverlap = train_nonoverlap_count(panel, train_indices, horizon)
        y_train = panel.loc[train_indices, target].to_numpy(float)
        c_train = panel.loc[train_indices, target_class].to_numpy(int)
        counts = np.array([(c_train == value).sum() for value in CLASSES], dtype=float)
        frequency = (counts + 1.0) / (len(c_train) + len(CLASSES))

        for model in MODEL_ORDER:
            if model == "baseline":
                prediction = 0.0
                probabilities = frequency
                interval_half = float(np.quantile(np.abs(y_train), 0.80))
                alpha_magnitude = np.nan
                alpha_class = np.nan
            else:
                alpha_magnitude, alpha_class = choose_alphas(panel, train_indices, model, horizon)
                x_train, processor = prepare_xy(panel, train_indices, model)
                x_live, _ = prepare_xy(panel, np.array([live_index]), model, processor)
                beta_magnitude, beta_class, fitted_frequency = fit_heads(
                    x_train, y_train, c_train, alpha_magnitude, alpha_class
                )
                magnitude, probability = predict_heads(
                    x_live, beta_magnitude, beta_class, fitted_frequency
                )
                prediction = float(magnitude[0])
                probabilities = probability[0]
                residuals = y_train - ridge_predict(beta_magnitude, x_train)
                inflation = math.sqrt(1.0 + x_train.shape[1] / max(len(x_train), 1))
                interval_half = float(np.quantile(np.abs(residuals), 0.80) * inflation)

            predicted_class = int(CLASSES[int(np.argmax(probabilities))])
            lower = prediction - interval_half
            upper = prediction + interval_half
            summary = summaries[(summaries["horizon"] == horizon) & (summaries["model"] == model)].iloc[0]
            mae_adjusted_row = adjustment[
                (adjustment["metric"] == "mae_skill_zero")
                & (adjustment["horizon"] == horizon)
                & (adjustment["model"] == model)
            ]
            brier_adjusted_row = adjustment[
                (adjustment["metric"] == "brier_skill_frequency")
                & (adjustment["horizon"] == horizon)
                & (adjustment["model"] == model)
            ]
            reasons = []
            if model == "baseline":
                reasons.append("baseline model")
            if train_nonoverlap < 20:
                reasons.append("independent training N<20")
            if summary["nonoverlap_n"] < 20:
                reasons.append("independent OOS N<20")
            if not (summary["mae_skill_zero_ci_low"] > 0):
                reasons.append("MAE skill CI includes zero")
            if model != "baseline":
                mae_adjusted_p = float(mae_adjusted_row.iloc[0]["max_null_adjusted_p"])
                brier_adjusted_p = float(brier_adjusted_row.iloc[0]["max_null_adjusted_p"])
                if mae_adjusted_p > 0.10:
                    reasons.append("MAE max-null adjusted p>0.10")
                if brier_adjusted_p > 0.10:
                    reasons.append("direction max-null adjusted p>0.10")
            else:
                mae_adjusted_p = np.nan
                brier_adjusted_p = np.nan
            if not (summary["phase_skill_positive_share"] >= 0.60):
                reasons.append("phase stability<60% positive")
            if not (summary["time_third_skill_min"] >= 0):
                reasons.append("negative time-third skill")
            if not bool(panel.at[live_index, "common_feature_quality"]):
                reasons.append("stale/missing live external input")
            confidence = float(np.max(probabilities))
            if confidence < 0.50:
                reasons.append("class confidence<0.50")

            holding_hurdle_rupee = 30.0 * horizon
            up_hurdle = math.log((current_price + holding_hurdle_rupee) / current_price)
            down_hurdle = abs(math.log((current_price - 100.0) / current_price))
            proposed = "NO CALL"
            if lower > up_hurdle and predicted_class == 1:
                proposed = "UP / HOLD"
            elif upper < -down_hurdle and predicted_class == -1:
                proposed = "DOWN / SELL"
            else:
                reasons.append(
                    f"80% interval/class does not clear holding hurdle Rs{holding_hurdle_rupee:.0f}"
                )
            decision = proposed if not reasons else "NO CALL"

            rows.append({
                "as_of": str(live_date.date()),
                "horizon": horizon,
                "model": model,
                "current_price": current_price,
                "provisional_credit_cost_rupee_per_mt_day": 30.0,
                "holding_hurdle_rupee": holding_hurdle_rupee,
                "loading_charge_rupee_per_mt_reference": 50.0,
                "predicted_log_return": prediction,
                "predicted_pct": math.expm1(prediction),
                "predicted_price": current_price * math.exp(prediction),
                "lower80_price": current_price * math.exp(lower),
                "upper80_price": current_price * math.exp(upper),
                "prob_down": float(probabilities[0]),
                "prob_flat": float(probabilities[1]),
                "prob_up": float(probabilities[2]),
                "predicted_class": predicted_class,
                "class_confidence": confidence,
                "train_raw_n": int(len(train_indices)),
                "train_nonoverlap_n": train_nonoverlap,
                "oos_raw_n": int(summary["raw_oos_n"]),
                "oos_nonoverlap_n": int(summary["nonoverlap_n"]),
                "oos_mae_skill_zero_log": float(summary["mae_skill_zero_log"]),
                "oos_mae_skill_ci_low": float(summary["mae_skill_zero_ci_low"]),
                "mae_max_null_adjusted_p": mae_adjusted_p,
                "direction_max_null_adjusted_p": brier_adjusted_p,
                "phase_skill_positive_share": float(summary["phase_skill_positive_share"]),
                "alpha_magnitude": alpha_magnitude,
                "alpha_class": alpha_class,
                "turkey_date": str(panel.at[live_index, "turkey_date"].date()),
                "turkey_symbol": panel.at[live_index, "Symbol"],
                "turkey_age": float(panel.at[live_index, "turkey_age"]),
                "local_date": str(panel.at[live_index, "local_date"].date()),
                "local_age": float(panel.at[live_index, "local_age"]),
                "proposed_signal_before_evidence_gates": proposed,
                "decision": decision,
                "no_call_reasons": "; ".join(dict.fromkeys(reasons)) if reasons else "all gates passed",
            })
    return pd.DataFrame(rows)


def no_call_summary(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (horizon, model), group in predictions.groupby(["horizon", "model"], sort=False):
        calls = group[group["operational_call_pti"] != "NO CALL"]
        signs = calls["operational_call_pti"].map({"UP / HOLD": 1, "DOWN / SELL": -1}).to_numpy(float)
        rows.append({
            "horizon": horizon,
            "model": model,
            "oos_n": int(len(group)),
            "called_n": int(len(calls)),
            "coverage": float(len(calls) / len(group)),
            "hit_rate": float((signs == np.sign(calls["actual_log_return"])).mean()) if len(calls) else np.nan,
            "mean_signed_rupee": float(np.mean(signs * calls["actual_change_rupee"])) if len(calls) else np.nan,
            "median_signed_rupee": float(np.median(signs * calls["actual_change_rupee"])) if len(calls) else np.nan,
        })
    return pd.DataFrame(rows)


def main() -> None:
    panel, data_audit = build_panel()
    panel = add_targets(panel)
    panel.to_csv(OUTPUTS / "master_panel_v2.csv", index=False)

    origin_counts = {}
    prediction_parts = []
    for horizon in HORIZONS:
        origins = common_origins(panel, horizon)
        origin_counts[str(horizon)] = int(len(origins))
        for model in MODEL_ORDER:
            prediction_parts.append(backtest_model(panel, horizon, model, origins))
            print(f"completed horizon={horizon} model={model} origins={len(origins)}", flush=True)
    predictions = pd.concat(prediction_parts, ignore_index=True)

    for horizon in HORIZONS:
        expected = None
        for model in MODEL_ORDER:
            dates = predictions[
                (predictions["horizon"] == horizon) & (predictions["model"] == model)
            ]["origin_date"].reset_index(drop=True)
            expected = dates if expected is None else expected
            assert dates.equals(expected), f"Origin mismatch at {horizon}d/{model}"

    predictions = add_point_in_time_calls(predictions)
    phases = phase_offset_stability(predictions)
    summaries = summarize_predictions(predictions, phases)
    pairwise = pairwise_same_origin(predictions)
    mae_adjustment, mae_null_metadata = max_null_adjustment(predictions, "mae_skill_zero")
    brier_adjustment, brier_null_metadata = max_null_adjustment(predictions, "brier_skill_frequency")
    adjustment = pd.concat([mae_adjustment, brier_adjustment], ignore_index=True)
    live = fit_live_forecasts(panel, summaries, adjustment)
    decisions = live[live["model"] == "combined"].copy()
    calls = no_call_summary(predictions)

    predictions.to_csv(OUTPUTS / "oos_predictions_v2.csv", index=False)
    summaries.to_csv(OUTPUTS / "backtest_summary_v2.csv", index=False)
    phases.to_csv(OUTPUTS / "phase_offset_stability_v2.csv", index=False)
    pairwise.to_csv(OUTPUTS / "same_origin_pairwise_v2.csv", index=False)
    adjustment.to_csv(OUTPUTS / "multiple_testing_v2.csv", index=False)
    calls.to_csv(OUTPUTS / "no_call_summary_v2.csv", index=False)
    live.to_csv(OUTPUTS / "live_forecasts_v2.csv", index=False)
    decisions.to_csv(OUTPUTS / "horizon_decisions_v2.csv", index=False)

    target_counts = {
        str(horizon): int(panel[f"target_ret_{horizon}"].notna().sum())
        for horizon in HORIZONS
    }
    nonoverlap_counts = {}
    for horizon in HORIZONS:
        eligible = panel[f"target_ret_{horizon}"].notna()
        frame = pd.DataFrame({
            "origin_date": panel.loc[eligible, "date"],
            "target_end": panel.loc[eligible, f"target_end_{horizon}"],
        })
        nonoverlap_counts[str(horizon)] = int(len(greedy_nonoverlap(frame)))

    metadata = {
        "study": "8ANI leakage-safe forecast study v2",
        "seed": SEED,
        "horizons_calendar_days": HORIZONS,
        "target_definition": "first 8ANI quote on/after origin+H, accepted only through origin+H+4 calendar days",
        "primary_magnitude_baseline": "zero log-return / random walk",
        "secondary_magnitude_baseline": "expanding trailing-120-label median",
        "direction_baselines": "expanding Laplace-smoothed down/flat/up frequencies and expanding majority class",
        "purge_rule": "training target_end must be strictly before forecast origin_date",
        "asof_rule": (
            "Turkey and Bhavnagar observations must be strictly before the mandi forecast date; "
            "the documented 10:30 India sale cutoff precedes typical same-day Ayron/mandi updates."
        ),
        "same_origin_rule": "all six models use the exact common-feature-quality forecast origins within each horizon",
        "model_features": MODEL_FEATURES,
        "nonlinear_terms": [
            "positive/negative standardized plate_melt_z60 hinges beyond +/-1",
            "positive/negative standardized scrap_ingot_z60 hinges beyond +/-1",
            "clipped standardized turkey_mom10 x local_ingot_mom10 interaction",
        ],
        "alpha_grid_nested": ALPHAS,
        "min_raw_train": MIN_RAW_TRAIN,
        "oos_origin_spacing_days": OOS_ORIGIN_SPACING_DAYS,
        "bootstrap_reps": BOOTSTRAP_REPS,
        "max_null_reps": MAX_NULL_REPS,
        "max_null": {
            "mae": mae_null_metadata,
            "brier": brier_null_metadata,
            "scope_note": (
                "Adjustment covers the declared 5 non-baseline models x 7 horizons. It uses final OOS loss "
                "differentials and does not rerun the full fitting pipeline inside every null replicate."
            ),
        },
        "input_hashes_sha256": {
            "mandi_master.csv": sha256(INPUTS / "mandi_master.csv"),
            "turkey_scrap_daily_nearby.csv": sha256(INPUTS / "turkey_scrap_daily_nearby.csv"),
            "bhavnagar_Bhavnagar_Prices.csv": sha256(INPUTS / "bhavnagar_Bhavnagar_Prices.csv"),
        },
        "data_audit": data_audit,
        "target_raw_counts": target_counts,
        "target_greedy_nonoverlap_counts": nonoverlap_counts,
        "common_oos_origin_counts": origin_counts,
        "assertions_passed": [
            "strict prior-date Turkey joins",
            "strict prior-date Bhavnagar joins",
            "calendar target tolerance",
            "purged training outcomes",
            "identical model origins within each horizon",
        ],
        "no_call_gates": [
            "independent OOS N >= 20",
            "moving-block MAE skill CI lower bound > 0",
            "max-null adjusted one-sided p <= 0.10",
            "at least 60% of usable phase-offset cohorts have positive skill",
            "no negative time-third skill",
            "live external data pass strict age/quality checks",
            "class confidence >= 0.50",
            "HOLD requires the 80% lower interval and UP class to clear provisional credit cost Rs30/MT/day x horizon",
            "SELL requires the 80% upper interval and DOWN class to clear one Rs100 quote increment",
        ],
        "limitations": [
            "Mandi history contains 87- and 96-day gaps; rolling internal features reset after gaps over 14 days.",
            "Turkey nearby series is mostly zero-volume and often zero-range; open interest and staleness are audited, not proof of executable liquidity.",
            "Bhavnagar and Turkey same-day values are deliberately withheld, which is conservative when publication timestamps are unknown.",
            "Long-horizon labels overlap heavily; raw forecast counts are not independent sample sizes.",
            "Residual intervals are training-residual intervals, not fully conformal guarantees.",
            "Holding hurdle uses the current 29-Jun-2026 SRIA term of Rs30/MT/day and is provisional; loading is separately shown at Rs50/MT.",
        ],
    }
    (OUTPUTS / "study_metadata_v2.json").write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
    (OUTPUTS / "multiple_testing_metadata_v2.json").write_text(
        json.dumps({"mae": mae_null_metadata, "brier": brier_null_metadata}, indent=2),
        encoding="utf-8",
    )

    compact = {
        "output_directory": str(OUTPUTS),
        "common_oos_origin_counts": origin_counts,
        "decisions": decisions[
            [
                "horizon", "predicted_pct", "predicted_price", "lower80_price", "upper80_price",
                "prob_down", "prob_flat", "prob_up", "decision", "no_call_reasons",
            ]
        ].to_dict(orient="records"),
        "best_mae_rows": summaries[summaries["model"] != "baseline"]
        .sort_values(["horizon", "mae_skill_zero_log"], ascending=[True, False])
        .groupby("horizon")
        .head(1)[["horizon", "model", "mae_skill_zero_log", "mae_skill_zero_ci_low", "nonoverlap_n"]]
        .to_dict(orient="records"),
    }
    print(json.dumps(compact, indent=2, default=str))


if __name__ == "__main__":
    main()
