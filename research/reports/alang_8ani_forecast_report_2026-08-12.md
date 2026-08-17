# Alang 8ANI forecast research

**Research cut:** 12 August 2026  
**Forecast origin:** close of the 11 August 2026 Alang quote  
**Current 8ANI:** ₹38,500/metric tonne  
**Primary decision:** **NO CALL at every requested horizon.** The 30–60 day center of gravity is down, but it does not clear the pre-registered evidence and uncertainty gates.

## Current horizon view

The table below is the combined regularized model. Turkey and Bhavnagar inputs are joined strictly from dates before the Alang forecast date. Targets are the first Alang quote on or after the stated calendar horizon, accepted no more than four days late. The 80% ranges are empirical training-residual ranges, not guaranteed confidence intervals.

| Horizon | Approx target date | Point move | Point price | 80% range | Down / flat / up | Independent OOS N | Carry hurdle at ₹30/day | Evidence-gated call |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 5d | 16 Aug | -0.36% | ₹38,361 | ₹37,719–39,013 | 48% / 19% / 33% | 31 | ₹150 | **NO CALL** |
| 10d | 21 Aug | -0.23% | ₹38,411 | ₹37,472–39,373 | 40% / 20% / 40% | 20 | ₹300 | **NO CALL** |
| 15d | 26 Aug | -0.25% | ₹38,403 | ₹37,063–39,791 | 46% / 17% / 37% | 16 | ₹450 | **NO CALL** |
| 30d | 10 Sep | -1.63% | ₹37,872 | ₹36,428–39,374 | 65% / 3% / 32% | 9 | ₹900 | **NO CALL** |
| 45d | 25 Sep | -2.29% | ₹37,620 | ₹35,922–39,398 | 64% / 6% / 30% | 7 | ₹1,350 | **NO CALL** |
| 60d | 10 Oct | -3.62% | ₹37,107 | ₹35,354–38,947 | 69% / 2% / 29% | 4 | ₹1,800 | **NO CALL** |
| 90d | 9 Nov | -3.13% | ₹37,295 | ₹35,213–39,500 | 64% / 2% / 35% | 3 | ₹2,700 | **NO CALL** |

These point estimates are useful scenario centers, not validated targets. At 30 and 45 days the model's raw out-of-sample MAE improved modestly, but both uncertainty ranges include zero skill and their independent samples are only 9 and 7. At 60 and 90 days the complex model underperformed the random-walk benchmark.

## The closest thing to an edge

The most repeatable feature remains relative plate richness versus melting grades, not a black-box model.

- Live plate–melt 60-observation z-score: **+1.40**. The direct 8ANI–Melt and 10ANI–Melt scores are **+1.46** and **+1.47**. All three indicate plate is rich versus the melt floor, historically a downside setup.
- For the pre-specified plate–melt rule at 30 calendar days: 238 called rows, 67.6% direction hit including flat outcomes, +2.20% average signed return, and ₹850 median signed change. A moving-block interval is +1.25% to +3.18% and the 49-test circular-shift adjusted probability is 0.0227.
- The decisive limitation is **19 independent 30-day episodes**, one short of the project's non-negotiable minimum of 20. At 45 days the adjusted probability is 0.0466, but there are only 12 independent episodes. Neither may be promoted to “validated.”
- At 15 days there are 35 independent episodes and the raw block interval is just positive, but the 49-test adjusted probability is 0.219. Here the sample-size gate passes and the multiple-testing gate fails.

No one rule/horizon passed every pre-specified gate: independent N at least 20, positive block-bootstrap lower bound, familywise adjusted probability at most 5%, positive worst phase cohort, and economic hit rate above 50%.

There is one external-signal clue worth preserving. The Turkey-feature model at 45 days improved multiclass Brier score by 0.187 versus expanding class frequencies, with max-null adjusted probability 0.0166 and 74.1% raw weekly-origin accuracy. But it has only 7 non-overlapping episodes, negative time-third magnitude skill, and unstable phase cohorts. It is a research lead, not a live edge.

## Why the live signals disagree

| Signal family | Latest state | Directional implication | Trust now |
|---|---:|---|---|
| Plate versus melt curve | plate–melt z +1.40; 8ANI–Melt z +1.46 | Down / sell strength at roughly 15–45 days | Best near-edge; 30d N=19 |
| Scrap versus Bhavnagar ingot | z +0.93 | Neutral; below the fixed ±1 call threshold | No call |
| Bhavnagar downstream momentum | ingot +0.74%; TMT +2.76% over 10 reported observations | Up / hold | Conflicts with grade curve |
| Turkey HMS nearby | roll-safe partial 20-session return -3.42% | Down | Mostly marked, not traded; no standalone validation |
| Current physical-supply scenario | 24 snapshot vessels / 292,809 LDT beached in the past 60d; 26 / 334,207 LDT in 90d | Potential 45–90d supply pressure | Forward-only; no historical vintages |

Ayron Mart's 11 August snapshot also shows Bhavnagar TMT at ₹47,500 versus Mumbai ₹46,600 and Mandi Gobindgarh ₹46,700, while Bhavnagar ingot is ₹40,300 versus Ahmedabad ₹40,200 and Mumbai ₹40,600. The local TMT premium is consistent with firm downstream conditions, which is why the short-horizon signal is not clean.

The current 70-vessel Alang snapshot is not a complete arrivals archive. Under government plate-yield midpoints and two illustrative gamma dismantling kernels, it implies roughly 58–68 thousand tonnes of incremental plate release over 30 days and 168–170 thousand tonnes over 90 days. These are supply scenarios only; they are not backtested forecasts.

## Operational interpretation

The SRIA reference terms supplied in the user's WhatsApp archive state next-day payment, ₹50/MT loading, and ₹30/MT/day credit charge. At that carry rate, a 30-day hold needs at least ₹900/MT of upside before considering other risk or execution costs; a 60-day hold needs ₹1,800/MT.

No combined-model lower interval clears the hold hurdle, and no sell interval lies wholly below the sell threshold. The statistically correct output is therefore **NO CALL**, not a forced prediction.

If an inventory decision must be made despite that uncertainty, the evidence supports a **risk-management lean toward selling strength / keeping inventory lighter than normal for the 30–60 day window**, not a full liquidation call. That lean comes from three aligned downside indicators—rich plate spreads, negative Turkey momentum, and a plausible future vessel-release wave—but it is explicitly weaker than a validated forecast. At 5–15 days, downstream momentum conflicts with those indicators, so avoid making the short-horizon decision from this model alone.

## What was tested

The primary study compared six same-origin models across seven horizons:

1. Random walk / zero-change baseline plus expanding class-frequency probabilities.
2. Internal ridge: plate–melt z, own 10-day momentum, EWMA volatility, unchanged-price fraction.
3. Internal plus Bhavnagar ingot/TMT and scrap–ingot relative value.
4. Internal plus Turkey within-contract 5/10-session momentum and volatility.
5. Combined local + Turkey + internal model.
6. A conservative nonlinear challenger with fixed spread hinges and one local/Turkey interaction.

All transforms, clipping, imputation, standardization, alpha choice, and intervals were fitted using past data only. Training labels had to end strictly before each forecast origin. OOS origins were spaced weekly and identical across models. Magnitude skill was tested versus the zero-change forecast; direction was tested with down/flat/up Brier score, log loss and class metrics. Dependence was handled with greedy non-overlap counts, phase-offset cohorts and moving-block bootstrap. A joint max-null adjustment covered 35 non-baseline model/horizon tests.

The best raw magnitude improvements were:

| Model | Horizon | Raw OOS N | Independent N | MAE improvement vs zero | Block interval | Verdict |
|---|---:|---:|---:|---:|---:|---|
| Local | 30d | 27 | 9 | +0.00415 log points (~9.7%) | -0.00331 to +0.01121 | Provisional only |
| Combined | 30d | 27 | 9 | +0.00388 (~9.1%) | -0.00568 to +0.01170 | Provisional only |
| Combined | 45d | 27 | 7 | +0.00320 (~6.1%) | -0.00724 to +0.01167 | Provisional only |

The nonlinear challenger did not improve robustness. Complexity did not rescue the sample-size problem.

## Data audit that materially changed the result

- Alang Mandi: 606 quotes from 11 December 2023 through 11 August 2026. Two missing blocks span 87 and 96 days. Rolling state is reset across gaps over 14 days.
- The requested horizons are calendar days. Five, 10, 15, 30, 45, 60 and 90 quote observations actually span median 6, 13, 19, 39, 59, 79 and 118 calendar days. Earlier row-horizon results are not the requested forecast horizons.
- Turkey daily-nearby: 873 rows, 43 contracts and 42 rolls. 89.35% of rows have zero volume and 88.32% have zero high–low range. There is a 37-day hole around August–September 2024.
- Barchart `Change` equals the raw cross-contract gap at all 42 switches. It is **not** a roll-neutral same-contract return. Roll-day returns are therefore missing and momentum/volatility windows are constrained to one symbol. Any result produced by treating `Change` as a roll adjustment was discarded.
- The single `C-U26` file is one September 2026 contract, not a continuous Turkey spot history. It has 67.7% zero-volume rows and becomes credibly liquid only near expiry.
- Bhavnagar: 581 dates with all TMT, ingot and billet fields from January 2023 through 10 August 2026. Same-day values are withheld because the documented 10:30 Alang sale cutoff precedes typical 11:00 local updates.
- Only 225 Mandi rows pass the common strict-prior local + within-contract Turkey feature quality gate. This is the real sample available to the complex model.

LME's settlement methodology explains why a zero-volume curve can still move: a five-lot pricing-window VWAP is used only when the threshold is met; otherwise a settlement waterfall can use trades, bids/offers, prior valuation, curve refinement or expert judgment. Same-date final Turkey prices are published after the Indian decision window. See the [LME cash-settled futures methodology](https://www.lme.com/-/media/Files/About/Regulation/Key-compliance-notices/CashSettled-Futures-Daily-Settlement-Prices-Methodology.pdf) and [historical cash-settled futures data page](https://www.lme.com/en/market-data/reports-and-data/historical-data-for-cash-settled-futures).

## The better external model to build next

The most direct missing causal chain is:

> India versus Bangladesh/Pakistan demolition economics → actual Alang beachings by vessel type/LDT → type-specific plate yield → distributed dismantling release → local yard inventory, conditioned on new-plate and furnace margins.

The public AlangToday extraction captured 70 current vessel records and 132 monthly ships/LDT records for 2016–2026. The monthly overlap with 8ANI is only 29 months; descriptive correlations from one to three months ahead range from -0.12 to +0.19 and are not stable enough to use. Worse, the old values were all fetched in August 2026 and lack original release timestamps. They are context, not a point-in-time backtest.

Start repeated daily or weekly snapshots now. Use vessel-type plate-yield priors from the [Government shipbreaking technical guideline](https://environmentclearance.nic.in/writereaddata/Form-1A/HomeLinks/TGM_Ship%20Breaking%20Yards_010910_NK.pdf) and a distributed release kernel because dismantling commonly takes three to five months ([National Maritime Foundation analysis](https://maritimeindia.org/sustainable-ship-recycling-in-india-legal-economic-and-political-analysis/)). Add weekly destination offers/sales, daily [LME CFR India scrap](https://www.lme.com/metals/ferrous/lme-steel-cfr-india-platts), FBIL USD/INR, and local HR plate prices.

One terminology issue must also be confirmed before estimating yields: BigMint's public table calls roughly 12–14 mm plate “8 ANE,” while 6–8 mm is “4 ANE” ([BigMint grade table](https://www.bigmint.co/scrapmetallics?tab=tenders)). The model retains the user's `8ANI` label exactly and does not silently remap it.

## Reproducibility

- [`forecast_study_v2.py`](../src/forecast_study_v2.py): primary purged multi-model study.
- [`rule_validation.py`](../src/rule_validation.py): pre-specified threshold rules and candidate-level 49-test adjustment.
- [`external_csv_audit.json`](../outputs/external_csv_audit.json): detailed Turkey/market-file audit.
- [`external_driver_evidence.md`](external_driver_evidence.md): causal driver research and point-in-time acquisition schema.
- [`monthly_supply_study.py`](../src/monthly_supply_study.py): current-vintage supply context test.
- [`live_supply_inventory.py`](../src/live_supply_inventory.py): forward-only vessel-release scenarios.
- [`horizon_decisions_v2.csv`](../outputs/v2/horizon_decisions_v2.csv): exact live horizon table.
- [`backtest_summary_v2.csv`](../outputs/v2/backtest_summary_v2.csv): all primary model metrics.
- [`rule_backtest_summary.csv`](../outputs/rule_backtest_summary.csv): all 49 rule/horizon results.

The model is designed to say “no call” when the evidence is insufficient. That is the result here: a credible 30–45 day downside **near-edge**, but no fully validated forecast at any requested horizon yet.
