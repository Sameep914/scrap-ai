from pathlib import Path
import json
import pandas as pd
import numpy as np

root = Path(r"C:\Users\demos\OneDrive\Documents\ChatGPT\Scrap AI\research")
df = pd.read_csv(root / "inputs" / "turkey_scrap_daily_nearby.csv")
df["date"] = pd.to_datetime(df["Time"], errors="coerce")
df = df[df["date"].notna()].sort_values("date").reset_index(drop=True)
for c in ["Open", "High", "Low", "Latest", "Change", "Volume", "Open Int"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")
df["roll"] = df["Symbol"].ne(df["Symbol"].shift())
df["ret"] = np.log(df["Latest"]).diff()
rolls = df.loc[df["roll"], ["date", "Symbol", "Latest", "Volume", "Open Int", "ret"]].copy()
summary = {
    "rows": len(df), "first": str(df.date.min().date()), "last": str(df.date.max().date()),
    "contracts": int(df.Symbol.nunique()), "rolls": int(df.roll.sum() - 1),
    "zero_volume_rate": float(df.Volume.eq(0).mean()), "zero_oi_rate": float(df["Open Int"].eq(0).mean()),
    "zero_range_rate": float(df.High.eq(df.Low).mean()),
    "return_std_nonroll": float(df.loc[~df.roll, "ret"].std()),
    "return_std_roll": float(df.loc[df.roll & df.ret.notna(), "ret"].std()),
    "largest_abs_returns": df.assign(abs_ret=df.ret.abs()).sort_values("abs_ret", ascending=False).head(15)[["date","Symbol","Latest","ret","Volume","Open Int","roll"]].astype({"date":str}).to_dict("records"),
    "roll_table": rolls.astype({"date":str}).to_dict("records"),
}
(root / "outputs" / "turkey_nearby_audit.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
