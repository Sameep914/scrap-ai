# Handoff prompt — Alang scrap price model

Copy everything below into GPT along with `SBIP_Model_Clean.xlsx`.

---

## What you're working on

I run ship-recycling at Alang, Gujarat. I sell scrap into the domestic market. I'm building a model to predict **8ANI** (8mm plate scrap, the highest-volume grade) so I know when to hold inventory and when to sell.

The attached workbook has ~600 days of real mandi price data plus supporting series. Read the **START HERE**, **VALIDATED SIGNALS**, and **DATA WANTED** sheets first.

## Ground rules — these matter more than any result you produce

This project has produced **five false positives** that looked strong and collapsed under stricter testing. Every one came from the same handful of mistakes. Don't repeat them:

1. **Never test daily returns on the mandi series.** Mandi rates quote in ₹100 steps and don't move every day. Daily "returns" are quoting noise, not economics. This one error made us wrongly conclude for hours that scrap prices had no relationship to anything. Test **levels** and **multi-week changes** (10d, 20d, 30d).

2. **Always use walk-forward validation with purging.** Fixed train/test splits flatter results badly — one model showed 70-73% on a 60/40 split and 36-50% under walk-forward. When testing horizon *h*, drop training rows whose target window overlaps the test point.

3. **Check the median across combinations, never the best.** We tested 25 model/horizon combos and the best showed +15.1pp edge — but the expected best-of-25 from *pure chance* was +15.6pp. Mean edge was negative. Always compute what chance alone would produce.

4. **Rolling z-scores only, never full-sample.** Full-sample means/stds leak future information. Use trailing 60-120 day windows.

5. **VIF > 5 = reject the combination.** Combining ingot + billet (VIF 13-14) made the model *worse* than either alone.

6. **Report sample size with every result.** N < 20 independent observations means nothing, however good the number looks.

## What's already validated (don't re-derive, build on it)

| Signal | Mechanism | Best result | N |
|---|---|---|---|
| **Plate-melt spread** | 8ANI − Melt grade, rolling 60d z. High z (plate rich) → 8ANI falls | 30d: 79% fell, −2.93% avg, p<0.000001 | 130-162/side |
| **Value + momentum combo** | scrap/ingot z + ingot 10d mom + TMT 10d mom | 10d: buy 68% up, sell 65% down, p<0.000001 | 59/89 |
| **Cheap-side ratio** | 8ANI/ingot z < −1.0 → expect rise | 20d: 79.7% rose, +4.80% | 59 |
| **Ingot momentum** | Cost pass-through, ingot leads scrap | 10d: 1.90pp spread, p<0.0001 | 105/129 |
| **GARCH(1,1)** | Predicts *volatility*, not direction | Currently elevated (0.97% vs 0.86%) | 605 |

**Structural finding:** scrap leads ingot/billet/TMT downstream (IRF cumulative +0.80 to +0.83), not the reverse. Scrap is the input cost; mills reprice to protect margin.

**Ruled out (tested clean, no edge):** own-price technicals alone, USD/INR alone, iron ore alone, coking coal, TMT alone, cointegration with TMT (p=0.30), magnitude/price-level prediction (negative OOS R² at every horizon — direction works, magnitude doesn't).


## Lead times — how far ahead each factor acts

Measured by scanning every lag 1-45 days and finding where correlation peaks:

| Factor | Peak lead | Corr | Significant range | N | Trust |
|---|---|---|---|---|---|
| Plate-melt spread z | **35-40 days** | −0.41 | day 10-45 | ~540 | HIGH |
| Scrap/Ingot ratio z | **40-45 days** | −0.52 | day 1-45 | 213 | HIGH |
| TMT 10d momentum | **19 days** | +0.33 | day 3-45 | 314 | HIGH |
| Ingot 10d momentum | **19 days** | +0.16 | day 1-25 | 319 | MEDIUM |
| Iron ore 20d change | 29-45 days | −0.16 | day 29-45 | 398 | MEDIUM |
| USD/INR 20d change | 6 days | +0.58 | day 1-20 | 36 | LOW (n too small) |
| Turkey scrap 20d change | 40-45 days | −0.91 | day 14-45 | 36 | LOW (n too small) |
| China HRC 20d change | 14 days | −0.35 | not significant | 30 | LOW |

**Key structural insight:** the momentum signals and the value spreads run on different clocks. TMT/ingot momentum peaks at ~19 days. The relative-value spreads peak at 40-45 days and get *stronger* with longer lags (plate-melt is −0.05 at 5 days but −0.41 at 40 days). That's why combining them works — they're not redundant.

**Practical split:** momentum for 2-3 week decisions, spreads for 6-week planning.

## What I want you to do

**Priority 1 — get more data.** See the **DATA WANTED** sheet for exact sources and steps. The single highest-value item: **Turkey scrap full history from Barchart** (symbol C-U26 and older contracts). Its 30-day change correlation with Alang is **+0.868** but we only have 85 overlapping days. Extending this could unlock a validated global signal.

**Priority 2 — test these specific untried ideas:**

- **Cross-city spreads.** We have Bhavnagar ingot/billet/TMT. Get Ahmedabad, Mumbai, Mandi Gobindgarh from Ayron Mart. Regional arbitrage spreads are likely a new signal — the plate-melt spread (our strongest) came from exactly this kind of within-data relationship nobody thinks to check.
- **More intra-mandi spreads.** We tested plate-melt, heavy-light, 8ANI−1kgr. There are 10 grades — test all pairs systematically, with multiple-testing correction.
- **Regime conditioning.** Does the signal behave differently in monsoon (Jun-Sep) vs rest of year? During elevated GARCH volatility vs calm? We have the volatility model but never conditioned signals on it.
- **Mill price-hike events.** SAIL/JSW/Tata announce discrete hikes that move the whole chain. Confirmed real (TMT rose after every logged event, +0.6% to +5.5%) but only 3 event-clusters so far. Compile 20+ from steelmath.com/articles and test properly.
- **Non-linear / interaction effects.** All signals so far are linear-ish thresholds. Try gradient boosting on the *validated* features only (plate-melt z, ratio z, ingot momentum) — not a kitchen-sink search.

**Priority 3 — combine into one forecast.** We have several signals that each work at different horizons. Build a single composite that weights them by their measured reliability, with an explicit "no call" zone. Roughly a third of days should return no signal — that's correct behaviour, not a flaw.

## Current state (as of 11 Aug 2026)

- 8ANI: ₹38,500 · Ingot (Bhavnagar): ₹40,600 · TMT (Bhavnagar): ₹47,800
- Plate-melt spread z: **+1.46** (plate rich → 30-day read is DOWN)
- Scrap/ingot z: +1.61 (scrap rich vs ingot)
- Composite value+momentum score: +0.01 (neutral, no call)
- GARCH volatility: elevated


## Fundamentals layer (context, not signal)

Collected but **not testable yet** — monthly data gives ~24 points over 2 years, same sample-size wall that makes Turkey scrap (n=36) untrustworthy. Use as demand-backdrop context, not model input.

**Structural facts that matter:**
- India generates 28-30 Mt scrap/yr against 38-40 Mt demand = **~10 Mt permanent deficit**. This is the structural bid under Alang prices.
- Scrap imports: 6.8 Mt FY24 → 7.7 Mt FY26. Sources: UAE 26%, UK 17%, USA 14%, Saudi 9%.
- Union Budget capex FY26-27: ₹12.2 lakh crore (up from ₹11.2). Roads alone ₹3.09 lakh crore.
- Crude steel production FY26: 169.2 Mt (+10.7% YoY). ~40% via EAF/induction (the scrap-consuming route).

**Monthly finished-steel trade collected** (steel.gov.in): Sep25 0.65 Mt imports, Oct25 0.45, Jan26 0.42, Feb26 0.36, Mar26 0.56, May26 0.69.

Tested imports vs 8ANI monthly average: corr +0.659 but **p=0.155, n=6 — meaningless, do not use**.

**Task for you:** collect steel.gov.in Monthly Economic Report going back 24+ months so this becomes testable. Also CGA monthly actual capex (cga.nic.in), cement production (Index of Eight Core Industries), and China steel/scrap export volumes.

**How to use it meanwhile:** as a tilt on signal confidence — strong backdrop (rising imports + capex) means trust BUY signals more and fade SELL signals; weak backdrop means the reverse.


## PRIORITY SHIFT: external factors, not more mandi mining

The mandi grade-curve signals are well-mined (plate-melt spread, PCA factors). **Do not keep re-testing internal mandi structure.** The goal is finding what EXTERNAL factor drives Alang prices.

### The honest pattern blocking us

| | Strong correlation | Weak correlation |
|---|---|---|
| **Small sample** | Turkey scrap (85d, +0.868), USD/INR (36d, +0.58), China HRC (58d, +0.737) | — |
| **Large sample** | — | Iron ore (433d, only −0.16) |

Every strong external correlation has too few observations. Every large sample is weak. **This is a data availability problem, not evidence external factors don't matter.**

### Highest-priority UNTESTED external factors

**1. Alang ship arrivals (monthly).** Closest external driver to the actual business — ships beached determines local scrap supply. Sources: GMB (Gujarat Maritime Board) monthly reports, BigMint shipbreaking coverage, Marine Insight. Known data points: FY2024-25 = 113 ships (20-year low), Apr-Aug 2025 = 44 ships (+13% YoY), 2024 = ~680,000 LDT (−35% YoY), capacity is 450 ships/4.5M LDT so running at 25-30%.

**2. Alang vs Bangladesh/Pakistan price gap.** Newly quantified: Alang offers shipowners **$500-510/LDT** vs Bangladesh **$540-550** and Pakistan **$525-530**. That $30-50 gap directly determines how many ships come to Alang. Source: GMS (Global Marketing Systems) weekly demolition reports — free email list.

**3. Mill price-hike events.** TMT rose after every logged SAIL/JSW/Tata announcement (+0.6% to +5.5%). Only 3 event-clusters so far; need 20+ from steelmath.com/articles.

### Tested and failed (don't redo)

- **Baltic Dry Index**: theory was high freight → owners keep ships → less scrap → prices up. Tested monthly (n=23-29): nothing significant at any lead 1-6 months, and the sign was *negative*, opposite to theory. Retest only via the full chain (BDI → arrivals → supply → price), not BDI → price directly.

### Lead times for grade-curve signals (for reference — these are done)

| Signal | Peak lead | Corr | Significant range |
|---|---|---|---|
| 10ANI−Melt spread z | **38 days** | −0.442 | day 10-60 |
| Composite plate-melt z | **38 days** | −0.411 | day 11-60 |
| PC1 (curve level) | 33 days | +0.361 | day 12-60 |
| PC2 (5kg factor) | **56 days** | +0.294 | day 17-60 |

All are 5-8 week signals — nearly useless under 10 days.

## How to report back

For every test: state the **sample size**, the **validation method**, whether it's **walk-forward or fixed-split**, and what **pure chance** would have produced given how many things you tried. If a result doesn't survive walk-forward, say so plainly rather than reporting the fixed-split number.

I'd rather have one honest modest signal than five impressive ones that break in live use.
