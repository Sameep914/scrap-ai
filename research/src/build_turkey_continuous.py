from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "research" / "inputs"
CONTRACT_DIR = INPUTS / "turkey_contracts"
NEARBY_PATH = INPUTS / "turkey_scrap_daily_nearby.csv"
OUTPUT_PATH = INPUTS / "turkey_scrap_overlap_adjusted.csv"
AUDIT_PATH = ROOT / "research" / "outputs" / "turkey_overlap_adjustment_audit.json"
MAX_PREVIOUS_GAP_DAYS = 7


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).str.replace("%", "", regex=False),
        errors="coerce",
    )


def load_nearby() -> pd.DataFrame:
    frame = pd.read_csv(NEARBY_PATH)
    frame["date"] = pd.to_datetime(frame["Time"], errors="coerce")
    frame = frame.loc[frame["date"].notna()].copy()
    for column in ["Open", "High", "Low", "Latest", "Change", "Volume", "Open Int"]:
        frame[column] = numeric(frame[column])
    frame = frame.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
    frame["Symbol"] = frame["Symbol"].astype(str).str.strip().str.upper()
    frame["roll"] = frame["Symbol"].ne(frame["Symbol"].shift())
    frame.loc[frame.index[0], "roll"] = False
    return frame


def load_contracts() -> pd.DataFrame:
    pieces: list[pd.DataFrame] = []
    for path in sorted(CONTRACT_DIR.glob("is7*_daily_historical-data-*.csv")):
        symbol = path.name.split("_", 1)[0].upper()
        frame = pd.read_csv(path)
        frame["date"] = pd.to_datetime(frame["Time"], errors="coerce")
        frame = frame.loc[frame["date"].notna()].copy()
        for column in ["Open", "High", "Low", "Latest", "Change", "Volume", "Open Int"]:
            frame[column] = numeric(frame[column])
        frame["Symbol"] = symbol
        frame["source_file"] = path.name
        pieces.append(frame)
    if not pieces:
        raise FileNotFoundError(f"No fixed-contract downloads found in {CONTRACT_DIR}")
    contracts = pd.concat(pieces, ignore_index=True)
    contracts = contracts.sort_values(["Symbol", "date"]).drop_duplicates(
        ["Symbol", "date"], keep="last"
    )
    contracts["fixed_prev_date"] = contracts.groupby("Symbol")["date"].shift()
    contracts["fixed_prev_latest"] = contracts.groupby("Symbol")["Latest"].shift()
    contracts["fixed_prev_gap_days"] = (
        contracts["date"] - contracts["fixed_prev_date"]
    ).dt.days
    contracts["same_contract_log_return"] = np.log(
        contracts["Latest"] / contracts["fixed_prev_latest"]
    ).where(contracts["fixed_prev_gap_days"].le(MAX_PREVIOUS_GAP_DAYS))
    return contracts.reset_index(drop=True)


def consecutive_rolling_sum(values: pd.Series, window: int) -> pd.Series:
    missing_group = values.isna().cumsum()
    return values.groupby(missing_group).transform(
        lambda group: group.rolling(window, min_periods=window).sum()
    )


def build() -> tuple[pd.DataFrame, dict]:
    nearby = load_nearby()
    contracts = load_contracts()

    fixed_columns = [
        "Symbol",
        "date",
        "Latest",
        "Change",
        "fixed_prev_date",
        "fixed_prev_latest",
        "fixed_prev_gap_days",
        "same_contract_log_return",
        "source_file",
    ]
    fixed = contracts[fixed_columns].rename(
        columns={
            "Latest": "fixed_latest",
            "Change": "fixed_change",
            "source_file": "fixed_source_file",
        }
    )
    out = nearby.merge(fixed, on=["Symbol", "date"], how="left", validate="one_to_one")
    out["fixed_price_match"] = np.isclose(
        out["Latest"], out["fixed_latest"], rtol=0.0, atol=1e-9, equal_nan=False
    )
    out["previous_nearby_symbol"] = out["Symbol"].shift()
    out["previous_nearby_date"] = out["date"].shift()
    out["previous_nearby_latest"] = out["Latest"].shift()
    out["raw_nearby_log_return"] = np.log(out["Latest"] / out["previous_nearby_latest"])

    incoming_previous = contracts[["Symbol", "date", "Latest"]].rename(
        columns={"date": "previous_nearby_date", "Latest": "incoming_latest_on_previous_nearby_date"}
    )
    out = out.merge(
        incoming_previous,
        on=["Symbol", "previous_nearby_date"],
        how="left",
        validate="many_to_one",
    )
    out["roll_basis_log"] = np.log(
        out["incoming_latest_on_previous_nearby_date"] / out["previous_nearby_latest"]
    ).where(out["roll"])
    out["roll_identity_error"] = (
        out["raw_nearby_log_return"]
        - out["same_contract_log_return"]
        - out["roll_basis_log"]
    ).where(out["roll"])

    # This is the investable information change: on a roll, use the incoming
    # contract's own close-to-close move. It retains the market move and removes
    # only the known incoming/outgoing basis measured at the prior shared close.
    out["overlap_adjusted_log_return"] = out["same_contract_log_return"]
    out["overlap_adjusted_log_index"] = out["overlap_adjusted_log_return"].fillna(0.0).cumsum()
    out["overlap_adjusted_index"] = 100.0 * np.exp(out["overlap_adjusted_log_index"])
    for lag in [5, 10, 20]:
        out[f"turkey_mom{lag}"] = consecutive_rolling_sum(
            out["overlap_adjusted_log_return"], lag
        )
    missing_group = out["overlap_adjusted_log_return"].isna().cumsum()
    out["turkey_rv10"] = out["overlap_adjusted_log_return"].groupby(missing_group).transform(
        lambda group: group.shift(1).rolling(10, min_periods=7).std(ddof=1)
    )
    out["turkey_zero_range20"] = (
        out["High"].eq(out["Low"]).astype(float).shift(1).rolling(20, min_periods=15).mean()
    )
    out["turkey_zero_oi20"] = (
        out["Open Int"].le(0).astype(float).shift(1).rolling(20, min_periods=15).mean()
    )

    rolls = out.loc[out["roll"]].copy()
    covered_rolls = rolls["overlap_adjusted_log_return"].notna()
    exact_basis = rolls["roll_basis_log"].notna()
    audit = {
        "nearby_rows": int(len(out)),
        "fixed_contract_files": int(contracts["source_file"].nunique()),
        "fixed_contract_symbols": int(contracts["Symbol"].nunique()),
        "fixed_contract_rows": int(len(contracts)),
        "nearby_exact_fixed_matches": int(out["fixed_price_match"].sum()),
        "nearby_rows_without_exact_fixed_price": int((~out["fixed_price_match"]).sum()),
        "rolls": int(len(rolls)),
        "rolls_with_same_contract_return": int(covered_rolls.sum()),
        "rolls_with_prior_date_basis": int(exact_basis.sum()),
        "max_abs_roll_identity_error": (
            float(rolls.loc[exact_basis, "roll_identity_error"].abs().max())
            if exact_basis.any()
            else None
        ),
        "adjusted_return_nonmissing": int(out["overlap_adjusted_log_return"].notna().sum()),
        "mom10_nonmissing": int(out["turkey_mom10"].notna().sum()),
        "mom20_nonmissing": int(out["turkey_mom20"].notna().sum()),
        "method": (
            "At each nearby date use the selected fixed contract's own close-to-close log return. "
            "On a symbol switch this exactly removes the incoming/outgoing basis measured on the "
            "previous shared close while preserving the incoming contract's market move."
        ),
    }
    return out, audit


def main() -> None:
    frame, audit = build()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUTPUT_PATH, index=False, date_format="%Y-%m-%d")
    AUDIT_PATH.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
