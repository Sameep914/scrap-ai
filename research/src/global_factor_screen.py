from __future__ import annotations

import csv
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "inputs"
ENGINE = INPUTS / "engine_context"
DOWNLOADS = Path(r"C:\Users\demos\Downloads")
OUTPUTS = ROOT / "outputs" / "global_factor_screen"
HORIZONS = [5, 10, 15, 30, 45, 60, 90]
RNG = np.random.default_rng(20260812)


def correlation(x: np.ndarray, y: np.ndarray) -> float:
    valid = np.isfinite(x) & np.isfinite(y)
    x = np.asarray(x, dtype=float)[valid]
    y = np.asarray(y, dtype=float)[valid]
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return math.nan
    return float(np.corrcoef(x, y)[0, 1])


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    x_rank = pd.Series(np.asarray(x, dtype=float)).rank(method="average").to_numpy()
    y_rank = pd.Series(np.asarray(y, dtype=float)).rank(method="average").to_numpy()
    return correlation(x_rank, y_rank)


def number(value: object) -> float:
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return math.nan


def load_mandi() -> pd.DataFrame:
    frame = pd.read_csv(INPUTS / "mandi_master.csv")
    frame["date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame["price"] = pd.to_numeric(frame["8ANI"], errors="coerce")
    frame = frame.dropna(subset=["date", "price"]).sort_values("date").drop_duplicates("date")
    frame = frame.reset_index(drop=True)
    gaps = frame["date"].diff().dt.days.gt(7)
    frame["gap_counter"] = gaps.cumsum()
    dates = frame["date"].to_numpy(dtype="datetime64[ns]")
    prices = frame["price"].to_numpy(float)
    gap_count = frame["gap_counter"].to_numpy(int)
    for horizon in HORIZONS:
        endpoint = np.searchsorted(dates, dates + np.timedelta64(horizon, "D"), side="left")
        valid = endpoint < len(frame)
        elapsed = np.full(len(frame), np.nan)
        rows = np.flatnonzero(valid)
        elapsed[rows] = (dates[endpoint[rows]] - dates[rows]) / np.timedelta64(1, "D")
        valid &= elapsed <= horizon + 4
        rows = np.flatnonzero(valid)
        valid[rows] &= gap_count[endpoint[rows]] == gap_count[rows]
        end_date = np.full(len(frame), np.datetime64("NaT"), dtype="datetime64[ns]")
        target = np.full(len(frame), np.nan)
        rows = np.flatnonzero(valid)
        end_date[rows] = dates[endpoint[rows]]
        target[rows] = np.log(prices[endpoint[rows]] / prices[rows])
        frame[f"end_{horizon}"] = pd.to_datetime(end_date)
        frame[f"target_{horizon}"] = target
    return frame


def momentum_frame(name: str, dates: pd.Series, values: pd.Series, lags: list[int], cadence: str) -> list[dict]:
    frame = pd.DataFrame({"date": pd.to_datetime(dates), "value": pd.to_numeric(values, errors="coerce")})
    frame = frame.dropna().sort_values("date").drop_duplicates("date").reset_index(drop=True)
    output: list[dict] = []
    for lag in lags:
        feature = np.log(frame["value"] / frame["value"].shift(lag))
        item = frame.assign(feature=feature).dropna(subset=["feature"])[["date", "feature"]]
        output.append({"name": f"{name}_mom{lag}", "cadence": cadence, "data": item})
    return output


def parse_engine_monthly(path: Path, value_column: str, name: str) -> list[dict]:
    rows: list[tuple[pd.Timestamp, float]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 2 or not re.fullmatch(r"20\d{2}-\d{2}", row[0].strip()):
                continue
            value = number(row[1] if value_column == "second" else row[2])
            if np.isfinite(value):
                rows.append((pd.Timestamp(row[0] + "-01") + pd.offsets.MonthEnd(0), value))
    data = pd.DataFrame(rows, columns=["date", "value"]).drop_duplicates("date", keep="last")
    return momentum_frame(name, data["date"], data["value"], [1, 3], "monthly")


def load_usdinr_monthly() -> list[dict]:
    return parse_engine_monthly(ENGINE / "usd_inr.csv", "second", "usdinr")


def load_china_hrc() -> list[dict]:
    weekly: list[tuple[pd.Timestamp, float]] = []
    monthly: list[tuple[pd.Timestamp, float]] = []
    with (ENGINE / "china_hrc_fob.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 2:
                continue
            token = row[0].strip()
            value = number(row[1])
            if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", token) and np.isfinite(value):
                weekly.append((pd.Timestamp(token), value))
            elif re.fullmatch(r"20\d{2}-\d{2}", token) and np.isfinite(value):
                monthly.append((pd.Timestamp(token + "-01") + pd.offsets.MonthEnd(0), value))
    weekly_frame = pd.DataFrame(weekly, columns=["date", "value"])
    monthly_from_weekly = (
        weekly_frame.set_index("date")["value"].resample("ME").last().dropna().reset_index()
    )
    monthly_frame = pd.concat(
        [monthly_from_weekly, pd.DataFrame(monthly, columns=["date", "value"])], ignore_index=True
    ).sort_values("date").drop_duplicates("date", keep="last")
    return (
        momentum_frame("china_hrc", weekly_frame["date"], weekly_frame["value"], [1, 4, 12], "weekly")
        + momentum_frame("china_hrc_monthly", monthly_frame["date"], monthly_frame["value"], [1, 3], "monthly")
    )


def load_turkey_monthly() -> list[dict]:
    rows: list[tuple[pd.Timestamp, float]] = []
    with (ENGINE / "turkey_hms_8020.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) < 3 or not re.fullmatch(r"20\d{2}-\d{2}", row[0].strip()):
                continue
            if row[1].strip() != "SC1!":
                continue
            value = number(row[2])
            if np.isfinite(value):
                rows.append((pd.Timestamp(row[0] + "-01") + pd.offsets.MonthEnd(0), value))
    frame = pd.DataFrame(rows, columns=["date", "value"]).drop_duplicates("date", keep="last")
    return momentum_frame("turkey_sheet", frame["date"], frame["value"], [1, 3], "monthly")


def load_supply_monthlies() -> list[dict]:
    section = ""
    values: dict[str, list[tuple[pd.Timestamp, float]]] = {"bdi": [], "iron_ore": [], "coking_coal": []}
    with (ENGINE / "supply_substitutes.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            joined = " ".join(row).upper()
            if "BALTIC DRY INDEX - FULL MONTHLY SERIES" in joined:
                section = "bdi"
                continue
            if "IRON ORE CFR CHINA" in joined:
                section = "iron_ore"
                continue
            if "COKING COAL - SGX" in joined:
                section = "coking_coal"
                continue
            if not section or len(row) < 2 or not re.fullmatch(r"20\d{2}-\d{2}", row[0].strip()):
                continue
            value = number(row[1])
            if np.isfinite(value):
                values[section].append(
                    (pd.Timestamp(row[0] + "-01") + pd.offsets.MonthEnd(0), value)
                )
    output: list[dict] = []
    for name, rows in values.items():
        frame = pd.DataFrame(rows, columns=["date", "value"]).drop_duplicates("date", keep="last")
        if len(frame) >= 4:
            output += momentum_frame(name, frame["date"], frame["value"], [1, 3], "monthly")
    return output


def load_barchart(path: Path, name: str, lags: list[int]) -> list[dict]:
    frame = pd.read_csv(path)
    frame["date"] = pd.to_datetime(frame["Time"], errors="coerce")
    frame["value"] = pd.to_numeric(frame["Latest"], errors="coerce")
    frame = frame.dropna(subset=["date", "value"])
    return momentum_frame(name, frame["date"], frame["value"], lags, "daily")


def load_daily_factors() -> list[dict]:
    specs = [
        ("usdinr_price-history-08-11-2026.csv", "usdinr_daily"),
        ("yqu26_price-history-08-11-2026.csv", "coking_coal_fixed"),
        ("v7q26_price-history-08-11-2026.csv", "china_hrc_fixed"),
        ("trq26_price-history-08-11-2026.csv", "iron_ore_fixed"),
        ("r-u26_daily_historical-data-08-11-2026.csv", "turkey_rebar_fixed"),
    ]
    output: list[dict] = []
    for filename, name in specs:
        output += load_barchart(DOWNLOADS / filename, name, [5, 20])
    turkey = pd.read_csv(INPUTS / "turkey_scrap_overlap_adjusted.csv")
    turkey["date"] = pd.to_datetime(turkey["date"], errors="coerce")
    for lag in [5, 10, 20]:
        item = turkey[["date", f"turkey_mom{lag}"]].rename(
            columns={f"turkey_mom{lag}": "feature"}
        ).dropna()
        output.append({"name": f"turkey_overlap_mom{lag}", "cadence": "daily", "data": item})

    scrap = pd.read_csv(INPUTS / "turkey_scrap_C_U26.csv")
    scrap["date"] = pd.to_datetime(scrap["Time"], errors="coerce")
    scrap["scrap"] = pd.to_numeric(scrap["Latest"], errors="coerce")
    rebar = pd.read_csv(DOWNLOADS / "r-u26_daily_historical-data-08-11-2026.csv")
    rebar["date"] = pd.to_datetime(rebar["Time"], errors="coerce")
    rebar["rebar"] = pd.to_numeric(rebar["Latest"], errors="coerce")
    spread = scrap[["date", "scrap"]].merge(rebar[["date", "rebar"]], on="date")
    spread["value"] = spread["rebar"] - spread["scrap"]
    output += momentum_frame("turkey_rebar_scrap_spread", spread["date"], spread["value"], [5, 20], "daily")
    return output


def independent_rows(frame: pd.DataFrame, horizon: int) -> pd.DataFrame:
    selected: list[int] = []
    next_date = pd.Timestamp.min
    for idx, row in frame.sort_values("date").iterrows():
        if row["date"] >= next_date:
            selected.append(idx)
            next_date = row[f"end_{horizon}"]
    return frame.loc[selected].sort_values("date")


def circular_p(x: np.ndarray, y: np.ndarray, observed: float, reps: int = 2000) -> float:
    if len(x) < 8 or not np.isfinite(observed):
        return math.nan
    exceed = 0
    for _ in range(reps):
        shift = int(RNG.integers(1, len(x)))
        rho = spearman(np.roll(x, shift), y)
        exceed += int(np.isfinite(rho) and abs(rho) >= abs(observed))
    return (exceed + 1) / (reps + 1)


def holm(pvalues: pd.Series) -> pd.Series:
    valid = pvalues.dropna().sort_values()
    adjusted = pd.Series(np.nan, index=pvalues.index, dtype=float)
    running = 0.0
    total = len(valid)
    for rank, (idx, value) in enumerate(valid.items()):
        running = max(running, min(1.0, (total - rank) * value))
        adjusted.loc[idx] = running
    return adjusted


def evaluate(mandi: pd.DataFrame, factor: dict, horizon: int) -> dict:
    feature = factor["data"].dropna().sort_values("date").drop_duplicates("date")
    merged = pd.merge_asof(
        mandi.sort_values("date"),
        feature.rename(columns={"date": "factor_date"}),
        left_on="date",
        right_on="factor_date",
        direction="backward",
        allow_exact_matches=False,
    )
    max_age = {"daily": 4, "weekly": 10, "monthly": 40}[factor["cadence"]]
    merged["factor_age"] = (merged["date"] - merged["factor_date"]).dt.days
    merged = merged.dropna(subset=["feature", f"target_{horizon}", f"end_{horizon}"])
    merged = merged[merged["factor_age"].le(max_age)]
    # Never count a repeated forward-filled native observation as new evidence.
    merged = merged.sort_values("date").drop_duplicates("factor_date", keep="first")
    independent = independent_rows(merged, horizon)
    x = independent["feature"].to_numpy(float)
    y = independent[f"target_{horizon}"].to_numpy(float)
    if len(independent) >= 3 and np.std(x) > 0 and np.std(y) > 0:
        spear = spearman(x, y)
        pear = correlation(x, y)
    else:
        spear = pear = math.nan
    half = len(independent) // 2
    first = spearman(x[:half], y[:half]) if half >= 4 else math.nan
    second = spearman(x[half:], y[half:]) if len(x) - half >= 4 else math.nan
    return {
        "factor": factor["name"],
        "cadence": factor["cadence"],
        "horizon": horizon,
        "native_matched_n": int(len(merged)),
        "independent_n": int(len(independent)),
        "spearman": spear,
        "pearson": pear,
        "circular_shift_p": circular_p(x, y, spear),
        "first_half_spearman": first,
        "second_half_spearman": second,
        "stable_sign": bool(np.isfinite(first) and np.isfinite(second) and first * second > 0),
        "first_date": str(independent["date"].min().date()) if len(independent) else "",
        "last_date": str(independent["date"].max().date()) if len(independent) else "",
    }


def main() -> None:
    mandi = load_mandi()
    factors = (
        load_usdinr_monthly()
        + load_china_hrc()
        + load_turkey_monthly()
        + load_supply_monthlies()
        + load_daily_factors()
    )
    rows = [evaluate(mandi, factor, horizon) for factor in factors for horizon in HORIZONS]
    result = pd.DataFrame(rows)
    result["holm_adjusted_p"] = holm(result["circular_shift_p"])
    result["screen_pass"] = (
        result["independent_n"].ge(20)
        & result["holm_adjusted_p"].le(0.10)
        & result["stable_sign"]
    )
    result = result.sort_values(
        ["screen_pass", "holm_adjusted_p", "independent_n"], ascending=[False, True, False]
    )
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUTS / "native_factor_correlations.csv", index=False)
    print(result.head(30).to_string(index=False))
    print("passes", int(result["screen_pass"].sum()), "of", len(result))


if __name__ == "__main__":
    main()
