# External driver evidence for Alang 8ANI forecasting

**Research cut:** 12 August 2026. **Decision:** which external variables can add causal, point-in-time signal at 5, 10, 15, 30, 45, 60 and 90-day horizons.

## Technical summary

- The highest-priority forecast layer is a physical Alang supply chain: **India-versus-rival ship purchase economics → actual beachings by vessel type and LDT → type-specific plate yield → distributed dismantling release → local plate scarcity/margins**. This is more direct than generic construction or Turkey scrap alone.
- The existing local grade curve, melt/attachment prices, Bhavnagar TMT/ingot/billet prices and the Turkey nearby series can be tested immediately. A newly captured AlangToday monthly series can be tested as a slow supply-regime variable, but it is a **current-vintage history**, not point-in-time proof.
- The newly captured 70-vessel AlangToday table is useful for the **live** 30–90 day forecast, but not for historical backtesting until repeated snapshots create a vintage archive. Its 70 rows sum to 1,150,384 LDT and contain beaching dates from 2020 through 4 August 2026, showing that it is a current stock table rather than a complete event history.
- The next acquisitions should be weekly India/Bangladesh/Pakistan demolition offers and sales, daily LME CFR India scrap plus USD/INR, and repeated Alang vessel snapshots. Mill operating rates and local HR plate prices would be especially valuable but do not have a reliable public Bhavnagar history.
- Confirm the grade definition before modeling. BigMint's public convention labels **8 ANE as 12–14 mm**, while 6–8 mm is 4 ANE ([grade table](https://www.bigmint.co/scrapmetallics?tab=tenders)). If the target is literally 8 mm rather than the yard's “8ANI/8ANE” grade, the yield and substitution mapping must be changed.

## Forecast layer by horizon

Status labels are: **TEST NOW** = usable from files already in this study; **FORWARD ONLY** = usable for the current/live forecast but lacks point-in-time history; **ACQUIRE** = source identified but series not yet ingested.

| Horizon | Causal driver and feature | Expected mechanism | Status |
|---|---|---|---|
| 5–10 days | Local grade curve; `8ANI − Melt`, `8ANI − 6ANI`, `10ANI − 8ANI`; local momentum and staleness | Measures immediate thickness scarcity, melt-floor movement and quote adjustment | **TEST NOW** from [`mandi_master.csv`](../inputs/mandi_master.csv), 606 quotes from 11 Dec 2023 to 11 Aug 2026 |
| 5–15 days | Bhavnagar `TMT − 8ANI`, `Ingot − Melt`, `Billet − 8ANI`; add local HR plate/HRC minus 8ANI | Positive conversion/substitution margin should strengthen plate demand; QCO policy can change the TMT relationship | **TEST NOW** for TMT/ingot/billet from [`bhavnagar_Bhavnagar_Prices.csv`](../inputs/bhavnagar_Bhavnagar_Prices.csv); **ACQUIRE** HR plate/HRC |
| 5–15 days | `CFR India scrap × USDINR + landed cost − local Melt` | Imported parity moves the melt floor and furnace charge economics | **ACQUIRE** LME CFR India and FBIL FX; Turkey nearby is only a global control |
| 15–30 days | `India USD/LDT offer − max(Bangladesh, Pakistan offer)` by vessel class; actual reported sales | A higher relative Indian bid raises the probability that demolition candidates are sold to Alang | **ACQUIRE** weekly Best Oasis/GMS PDFs and sales records |
| 30–45 days | New beachings: LDT, vessel type, beaching date; early release kernel | Beaching converts a purchase into visible future inventory; cutting begins before most hull plate reaches the market | **FORWARD ONLY** from the 70-row current snapshot; monthly aggregate LDT/count is **TEST NOW** as a slow regime feature |
| 45–90 days | `effective_plate_supply = Σ LDT_i × yield_type_i × release_kernel(age_i)` | Type-adjusted, age-weighted yard inventory should predict when rerollable plate becomes abundant or scarce | **FORWARD ONLY** until repeated ship snapshots create vintages; historical monthly LDT/count can provide a low-frequency prior |
| 60–90+ days | Bulker/tanker/container charter earnings | Strong vessel earnings delay retirement and reduce demolition supply; class matching matters | **ACQUIRE** licensed Baltic/HARPEX-class history |
| 45–90 days | HS 7204 scrap imports, flat-steel imports, JPC steel production/consumption, fabricated-metal/machinery IIP, tractors/equipment | Imports change melt availability; fabrication and machinery are closer end-use proxies than cement alone | **ACQUIRE** official monthly series and use only after publication timestamp |
| 90+ days | Cement, infrastructure goods, roads and government capex | Slow demand regime, not a credible primary short-horizon plate signal | **ACQUIRE last**; likely little incremental power inside 90 days |

The proposed supply feature is:

```text
relative_offer[class,t] = India_offer_USD_per_LDT
                          - max(Bangladesh_offer, Pakistan_offer)

plate_potential[i] = vessel_LDT[i] × rerollable_yield[vessel_type[i]]

effective_plate_supply[t] = Σ plate_potential[i]
                              × release_kernel(age_since_beaching[i], vessel_type[i])
```

Government technical guidance estimates rerollable plate at 56–70% of LDT for general cargo vessels, 61–71% for bulkers, 72–81% for tankers and 63–67% for container ships; melting scrap is generally 5–10% ([Government shipbreaking technical guideline](https://environmentclearance.nic.in/writereaddata/Form-1A/HomeLinks/TGM_Ship%20Breaking%20Yards_010910_NK.pdf)). These are priors, not fixed coefficients. National Maritime Foundation reports that a 10,000–20,000 LDT vessel commonly takes roughly three to five months to dismantle ([economic/legal analysis](https://maritimeindia.org/sustainable-ship-recycling-in-india-legal-economic-and-political-analysis/)); fit a gamma or Weibull release kernel rather than imposing a single 45- or 60-day lag.

## What can be tested immediately

1. **Local price-chain features.** Use the existing grade, melt and attachment family plus Bhavnagar TMT/ingot/billet. Test levels only through cointegration/error-correction or spreads; daily price levels will otherwise produce spurious correlations. Add staleness/age because the target is not quoted every calendar day.
2. **Turkey scrap as a global factor.** [`turkey_scrap_daily_nearby.csv`](../inputs/turkey_scrap_daily_nearby.csv) has 873 dated observations from 12 Jan 2023 to 11 Aug 2026. It is a stitched nearby curve with many zero-volume observations, so retain the existing volume, open-interest, roll and quality flags. Do not treat the Sep-2026 contract as a continuous history.
3. **Alang monthly supply regime.** The public AlangToday analysis year selector returned 132 monthly rows for 2016–2026. Complete-year totals vary materially—from 3.145 million LDT/287 ships in 2016 to 0.768 million LDT/108 ships in 2024 and 1.222 million LDT/121 ships in 2025. Jan–Aug 2026 shows 0.728 million LDT/69 ships, with August partial. This is useful for regime tests, but only 33 calendar months overlap the 8ANI series, including its partial first month.
4. **A live vessel-inventory feature.** For the current forecast, use the captured 70 ships' LDT, type and age since beaching. Apply broad type-yield priors and several release-kernel sensitivities. Do not claim a historical backtest until vintages have accumulated.

The AlangToday extraction used no authentication. It confirmed:

- [`all-demolition.aspx`](https://www.alangtoday.com/all-demolition.aspx) exposes 70 current rows over three public postback pages with name, former name, IMO, vessel type, LDT, country/year built, beaching date and propeller-shaft diameter. The diameter unit is not stated.
- [`alang-analysis.aspx`](https://www.alangtoday.com/alang-analysis.aspx) exposes monthly **LDT beached** and **number of ships beached** via an unauthenticated 2016–2026 year selector. Other advertised analysis fields, such as future daily production and detailed start/end lists, were empty or login-gated in the public response.
- The site itself disclaims accuracy and completeness. Historical chart values have no preserved original release timestamps or revision log.

Saved point-in-time artifacts, all acquired at **2026-08-12 10:03:35 UTC**:

- [70-row current demolition snapshot](../inputs/external/alangtoday_demolition_current_20260812T100336Z.csv)
- [2016–2026 monthly beachings snapshot](../inputs/external/alangtoday_monthly_beachings_2016_2026_asof_20260812T100336Z.csv)
- [Acquisition metadata and SHA-256 hashes](../inputs/external/alangtoday_snapshot_20260812T100336Z.metadata.json)
- [Reproducible read-only acquisition script](../src/acquire_alangtoday_snapshot.ps1)

The current table is a **snapshot only**. Its beaching dates do not make it a complete 2020–2026 arrivals archive. The monthly charts are confirmed historical series as rendered now, but they remain current-vintage data until repeated acquisitions establish revisions.

## Data-acquisition-only feature queue

| Priority | Frequency | Series to acquire | Source and coverage evidence | Why / limitation |
|---:|---|---|---|---|
| 1 | Daily snapshot or at least weekly | Full current Alang vessel table; track new IDs, changed fields and disappearance | [AlangToday recycling report](https://www.alangtoday.com/all-demolition.aspx) | Creates the missing point-in-time yard-inventory panel. Current page is commercial, revisable and not an official census. |
| 2 | Weekly | India, Bangladesh and Pakistan USD/LDT offers by bulker/tanker/container; actual sale price, LDT and destination | [Best Oasis archive](https://www.best-oasis.com/blogs-news); examples [29 Jun–5 Jul 2024](https://www.hellenicshippingnews.com/wp-content/uploads/2024/07/Weekly-Ship-Recycling-Report-29-June-05-July-2024_compressed.pdf) and [6–12 Dec 2025](https://www.hellenicshippingnews.com/wp-content/uploads/2025/12/Weekly-Ship-Recycling-Report-06-December-12-December-2025.pdf) | Direct destination-arbitrage signal. Commercial assessments, PDF format and sometimes approximate publication time. GMS reports can supplement but may require entitlement ([GMS Weekly](https://www.gmsinc.net/get-in-touch)). |
| 3 | Daily | LME Steel Scrap CFR India curve, volume/OI, and FBIL USD/INR | [LME CFR India](https://www.lme.com/metals/ferrous/lme-steel-cfr-india-platts), [LME historical XLSX](https://www.lme.com/en/Market-data/Reports-and-data/Historical-data-for-cash-settled-futures), [FBIL](https://www.fbil.org.in/) | True India import-parity factor. Platts changed the underlying India shredded assessment from weekly to daily on 3 Jun 2024 ([notice](https://www.spglobal.com/energy/en/pricing-benchmarks/our-methodology/subscriber-notes/060324-platts-moves-india-shredded-scrap-assessment-frequency-to-daily)); model that frequency break. Check LME/FBIL reuse terms. |
| 4 | Daily/weekly | Local HR plate/HRC, re-roller orders, utilization, electricity, dispatch and inventory | Local mills, SRIA, BigMint/Ayronmart | Closest demand evidence. No reliable open Bhavnagar operating-rate history was found; national electricity prices are a poor substitute. |
| 5 | Monthly | HS 7204 by origin/port and HS 7208 flat steel; quantity, value and unit value | [DGCIS TradeStat](https://tradestat.commerce.gov.in/ftspcc/import_commodity_wise) | Public history was available through Jun 2026 when checked. Release lag is commonly 45–60 days; reference month must never be used as availability date. |
| 6 | Monthly | Finished/crude steel production, consumption, imports/exports | Ministry of Steel [monthly economic reports](https://steel.gov.in/monthly-summary?page=0) | Official regime measures. Many tables are fiscal-year cumulative; difference carefully and preserve revisions. |
| 7 | Monthly | IIP fabricated metals, machinery and infrastructure/construction goods; core-industry steel/cement; Vahan tractors/equipment | [MoSPI metadata](https://nmds.mospi.gov.in/), [IIP manual](https://mospi.gov.in/sites/default/files/publication_reports/IIP_Manual_3apr18N1.pdf), [Eight Core Industries](https://www.data.gov.in/catalog/eight-core-industries), [Vahan](https://analytics.parivahan.gov.in/analytics/publicdashboard/vahan?lang=en) | Slow end-use controls. ICI was rebased to 2022-23 and expanded in Jul 2026 ([PIB release](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2286615&lang=2&reg=48)); Vahan coverage changes as RTOs join. |
| 8 | Daily/weekly | Class-specific bulker/tanker/container earnings | Baltic/other licensed vendors; [Baltic methodology](https://emissions.balticexchange.com/content/dam/balticexchange/consumer/documents/data-services/documentation/ocean-bulk-guides-policies/GMB.pdf) | Better demolition-supply lead than generic container freight. Most useful history is licensed. |
| 9 | 5–12 days | Sentinel-1/2 plot occupancy, hull length/area and new beaching detection | [Copernicus Data Space](https://dataspace.copernicus.eu/about), [Sentinel-2 details](https://dataspace.copernicus.eu/data-collections/copernicus-sentinel-missions/sentinel-2) | Experimental physical inventory. Sentinel-2 is 10 m with nominal five-day revisit; cloud, tide, SAR speckle and plot overlap require labelled validation. |
| 10 | Daily | Alang rainfall and tide | [IMD gridded rainfall](https://rcc.imdpune.gov.in/download.php/monitoring.php), [INCOIS tides](https://www.incois.gov.in/oceanservices/PAT/index.html) | Low-cost operational controls, probably only 0–10 day incremental signal. |

Annual sources should be validation only: [SRIA Alang ships/LDT history](https://www.sriaindia.in/alang-info.aspx), the NGO Shipbreaking Platform's [2013–2025 downloadable vessel lists](https://shipbreakingplatform.org/annual-lists/), and [UNCTAD ship-scrapping totals](https://unctadstat.unctad.org/datacentre/dataviewer/US.ShipScrapping). Annual retrospective lists must not be inserted into earlier forecasts before their actual publication dates.

## Point-in-time acquisition schema

Every raw observation should carry `series_id`, `observation_period`, `source_release_ts_utc`, `acquired_at_utc`, `vintage_id`, `value`, `unit`, `geography`, `quality_flag`, `source_url` and `raw_file_sha256`. `source_release_ts_utc` controls model availability; the economic reference date does not.

| Field(s) | Source / cadence | Release-timestamp rule | Unit | Caveat / quality flag |
|---|---|---|---|---|
| `quote_date`, `grade`, `location`, `price` | Local Alang grade quotes, daily | Exact publisher timestamp if available; otherwise acquisition time and make feature usable next quote session | INR/metric tonne | Record tax, freight, cash/credit and ex-yard basis; grade convention must be confirmed |
| `tmt`, `ingot`, `billet`, `hr_plate`, `hrc` | Bhavnagar/local steel, daily | Publisher time or conservative next-session timestamp | INR/metric tonne | Blank is “not reported,” not zero; preserve source-specific basis |
| `ship_id`, `imo`, `type`, `ldt`, `beached_date`, `built_year` | AlangToday current table, daily/weekly snapshot | **Use `acquired_at_utc`**, never beaching date, as the first-known timestamp | LDT metric tonnes; dates/counts | Current-state, revisable commercial table; archive raw hash and tombstones when ships disappear |
| `period_month`, `ldt_beached`, `ships_beached` | AlangToday analysis, monthly | Use acquisition time for the first archive; later vintages use each fetch time | metric tonnes; ship count | Original monthly release time unknown; current month partial; future zeros are placeholders |
| `country`, `vessel_class`, `offer_low`, `offer_high` | Best Oasis/GMS, weekly | PDF publication timestamp; if only week/date is printed, use first verified fetch or next market session | USD/LDT | Assessment, not necessarily executable bid |
| `vessel`, `imo`, `ldt`, `sale_price`, `destination`, `sale_date` | Weekly recycling sale reports | First report publication timestamp | USD/LDT; tonnes | Sale date can be revised; deduplicate by IMO and sale event |
| `trade_date`, `contract_month`, `settlement`, `volume`, `open_interest` | LME CFR India, daily | Official EOD publication timestamp | USD/metric tonne; contracts | Build constant maturity; flag rolls, zero volume and stale marks |
| `reference_date`, `usdinr` | FBIL, business daily | FBIL reference-rate publication timestamp | INR/USD | Licensing/reuse terms; do not substitute a later revised download silently |
| `index_date`, `vessel_class`, `charter_earnings` | Baltic/charter vendor, daily/weekly | Vendor publication timestamp | USD/day or index points | Match class to Alang vessel mix; licensed data |
| `reference_month`, `hs_code`, `origin`, `port`, `quantity`, `trade_value` | DGCIS, monthly | Dataset/publication timestamp, typically weeks after month-end | tonnes; INR/USD | Revision and unit-conversion risk; derive unit value only after quantity QA |
| `reference_month`, `production`, `consumption`, `imports`, `exports` | Ministry of Steel/JPC, monthly | Report posting timestamp | thousand/million tonnes | Convert cumulative fiscal-year tables to monthly flow; retain vintage |
| `reference_month`, `series`, `index`, `base_year` | MoSPI IIP / ICI, monthly | Official release timestamp | index points | Base-year/method breaks; no blind level splice |
| `month`, `state`, `rto_count`, `vehicle_category`, `registrations` | Vahan, monthly | Dashboard extraction timestamp | registrations | Coverage denominator changes; store reporting RTO count |
| `week_end`, `mill_id`, `utilization`, `orders`, `dispatch`, `inventory`, `electricity` | Local mill panel, daily/weekly | Survey/submission timestamp | %, tonnes, MWh | Proprietary sample; panel composition and non-response flags required |
| `scene_time`, `plot_id`, `vessel_area`, `hull_length`, `cloud`, `tide` | Sentinel-1/2 plus INCOIS, 5–12 days | Satellite acquisition time and product publication time | m², metres, %, metres | Measurement model required; keep sensor, orbit and processing version |
| `observation_time`, `rainfall`, `tide_height` | IMD/INCOIS, daily | Official product issue time | mm; metres | Weather station/grid selection and forecast-vs-observed status |

## End-use interpretation and structural breaks

Do not assume cement or public capex is the dominant 8ANI demand channel. National Maritime Foundation reports that post-QCO/BIS restrictions reduced direct reroll use of ship steel from roughly 70–80% to 40–50% ([analysis](https://maritimeindia.org/sustainable-ship-recycling-in-india-legal-economic-and-political-analysis/)). A sector study describes Bhavnagar/Sihor shifting toward agricultural equipment, engineering/fabrication and induction furnaces ([Turning the Tide](https://climatecatalyst.org/wp-content/uploads/2024/12/Turning-the-Tide-Ship-Recycling-as-a-Source-of-Green-Steel-in-India.pdf)). The better demand order is therefore local HR-plate substitution, fabrication/furnace margins, machinery/agricultural equipment, general steel demand, then construction/cement.

Include regime indicators for the QCO/BIS transition, flat-steel safeguard actions, Hong Kong Convention entry into force on 26 June 2025, and the Jul 2026 ICI rebasing. These are structural controls, not recurring tradable signals.

## Validation and failure modes

- There are only 606 target quotes and 33 overlapping calendar months, including the target's partial first month. Monthly variables should be low-dimensional regime priors, not a large ML feature block.
- Purge and embargo each walk-forward fold by the forecast horizon. Perform feature selection and lag selection inside each training fold, and compare against sticky-price/no-change and last-change baselines.
- Archive source vintages before claiming an edge. The new Alang monthly history can show association, but cannot by itself prove a point-in-time historical forecast because all old values were fetched in August 2026.
- Test calendar-day and quote-day horizons separately. On sparse quote dates, define the target as the first quote on or after the horizon and store the realized gap.
- Pre-register a small set of lag families—5/10/15 for local margins, 15/30/45 for offers and beachings, and 45/60/90 for effective supply—and correct for multiple testing.
- Estimate vessel-type kernels with shrinkage. The current table contains heterogeneous rigs, platforms, LNG ships, tankers and cargo vessels; applying one yield or one dismantling duration to all ships will be materially wrong.

## Recommended build order

1. Add the local conversion/substitution margins to the existing purged walk-forward study.
2. Add the acquired Alang monthly LDT/count only as one or two slow regime features and label the result current-vintage.
3. Start automated daily AlangToday snapshots now; build the live type-adjusted inventory feature from the 70-vessel baseline.
4. Backfill weekly rival-country offers/sales and daily LME CFR India plus FBIL FX with exact publication timestamps.
5. Seek a Bhavnagar mill panel and local HR plate series before spending effort on broad infrastructure/capex variables.
6. Promote a driver only if it improves signed accuracy or MAE across several adjacent horizons and survives vintage-safe walk-forward testing.
