import fs from "node:fs/promises";
import path from "node:path";
import { Workbook } from "@oai/artifact-tool";

const root = "C:/Users/demos/OneDrive/Documents/ChatGPT/Scrap AI";
const downloads = "C:/Users/demos/Downloads";
const outputPath = `${root}/research/outputs/external_csv_audit.json`;
const DAY_MS = 86_400_000;
const monthCodes = { F: 1, G: 2, H: 3, J: 4, K: 5, M: 6, N: 7, Q: 8, U: 9, V: 10, X: 11, Z: 12 };

const sourceSpecs = [
  {
    key: "usdinr",
    file: `${downloads}/usdinr_price-history-08-11-2026.csv`,
    identity: "USD/INR exchange-rate series; exact Barchart feed variant is not recoverable because the CSV omits Symbol and instrument metadata",
    identityConfidence: "partial",
    venue: "not stated in CSV",
    units: "INR per USD",
    verifiedUrl: "https://www.barchart.com/forex/quotes/USDINR.S/overview",
    relevance: "mandatory conversion factor for translating USD/t imported scrap and ferrous benchmarks into INR/t",
    decision: "include_after_obtaining_longer_history",
  },
  {
    key: "dce_coking_coal_yqu26",
    file: `${downloads}/yqu26_price-history-08-11-2026.csv`,
    identity: "DCE Hard Coking Coal September 2026 futures (YQU26)",
    identityConfidence: "verified",
    venue: "Dalian Commodity Exchange",
    units: "CNY per metric tonne",
    verifiedUrl: "https://www.barchart.com/futures/quotes/YQU26",
    relevance: "China steelmaking input and demand-cycle proxy; indirect for scrap because it primarily affects blast-furnace economics and substitution",
    decision: "experimental_regime_feature_only",
  },
  {
    key: "lme_hrc_fob_china_v7q26",
    file: `${downloads}/v7q26_price-history-08-11-2026.csv`,
    identity: "LME Steel HRC FOB China (Argus) August 2026 futures (V7Q26)",
    identityConfidence: "verified",
    venue: "London Metal Exchange",
    units: "USD per metric tonne",
    verifiedUrl: "https://www.barchart.com/futures/quotes/V7Q26/overview",
    relevance: "finished-steel and China export-demand proxy, but this is one short fixed-maturity contract",
    decision: "current_curve_cross_check_not_primary_backtest",
  },
  {
    key: "comex_iron_ore_trq26",
    file: `${downloads}/trq26_price-history-08-11-2026.csv`,
    identity: "COMEX Iron Ore CFR China (Platts) August 2026 futures (TRQ26)",
    identityConfidence: "verified_root_and_month_code",
    venue: "COMEX",
    units: "USD per dry metric tonne",
    verifiedUrl: "https://www.barchart.com/futures/quotes/TRF26",
    relevance: "upstream China steel-cycle and blast-furnace cost proxy; indirect for Indian plate scrap",
    decision: "exclude_from_return_model_use_only_as_flagged_settlement_curve_level",
  },
  {
    key: "lme_rebar_fob_turkey_ru26",
    file: `${downloads}/r-u26_daily_historical-data-08-11-2026.csv`,
    identity: "LME Steel Rebar FOB Turkey (Platts) September 2026 futures (R-U26)",
    identityConfidence: "verified",
    venue: "London Metal Exchange",
    units: "USD per metric tonne",
    verifiedUrl: "https://www.barchart.com/futures/quotes/R-U26",
    relevance: "direct same-region finished-steel margin/demand benchmark; economically strongest when paired with same-prompt Turkey scrap",
    decision: "include_same_prompt_rebar_minus_scrap_spread_with_settlement_quality_flag",
  },
  {
    key: "investing_hrc_china_empty",
    file: `${downloads}/STEEL HRC FOB CHINA Futures Historical Data (1).csv`,
    identity: "Investing.com Steel HRC FOB China continuous futures (MHCc1), header-only export",
    identityConfidence: "verified",
    venue: "London/LME-derived continuous series",
    units: "USD per metric tonne",
    verifiedUrl: "https://www.investing.com/commodities/lme-steel-hrc-fob-china-futures-historical-data",
    relevance: "none because the file contains no observations",
    decision: "exclude_empty",
  },
  {
    key: "investing_hrc_china_weekly",
    file: `${downloads}/STEEL HRC FOB CHINA Futures Historical Data (2).csv`,
    identity: "Investing.com Steel HRC FOB China continuous futures (MHCc1), weekly export",
    identityConfidence: "verified",
    venue: "London/LME-derived continuous series",
    units: "USD per metric tonne",
    verifiedUrl: "https://www.investing.com/commodities/lme-steel-hrc-fob-china-futures-historical-data",
    relevance: "longer finished-steel benchmark that overlaps most of the mandi sample, but roll methodology is opaque and frequency is weekly",
    decision: "include_weekly_only_with_strict_prior_date_and_no_daily_interpolation",
  },
  {
    key: "investing_hrc_china_daily_fragment",
    file: `${downloads}/STEEL HRC FOB CHINA Futures Historical Data.csv`,
    identity: "Investing.com Steel HRC FOB China continuous futures (MHCc1), short daily fragment",
    identityConfidence: "verified",
    venue: "London/LME-derived continuous series",
    units: "USD per metric tonne",
    verifiedUrl: "https://www.investing.com/commodities/lme-steel-hrc-fob-china-futures-historical-data",
    relevance: "same finished-steel benchmark as the weekly file but only a short October 2025 fragment",
    decision: "exclude_from_model_redundant_short_fragment",
  },
];

function parseDate(value) {
  let text = String(value ?? "").trim().replace(/^"|"$/g, "");
  if (/^\d+(?:\.\d+)?$/.test(text)) {
    const serial = Number(text);
    if (serial > 20_000 && serial < 80_000) {
      return new Date(Date.UTC(1899, 11, 30) + Math.round(serial) * DAY_MS);
    }
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return new Date(`${text}T00:00:00Z`);
  const us = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (us) return new Date(Date.UTC(Number(us[3]), Number(us[1]) - 1, Number(us[2])));
  return null;
}
const iso = (date) => date?.toISOString().slice(0, 10) ?? null;
const num = (value) => {
  const text = String(value ?? "").trim().replace(/,/g, "");
  if (!text) return null;
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : null;
};
const volumeNum = (value) => {
  const text = String(value ?? "").trim().replace(/,/g, "").toUpperCase();
  if (!text) return null;
  const match = text.match(/^([-+]?\d*\.?\d+)([KMB])?$/);
  if (!match) return null;
  const factor = match[2] === "K" ? 1_000 : match[2] === "M" ? 1_000_000 : match[2] === "B" ? 1_000_000_000 : 1;
  return Number(match[1]) * factor;
};
const pctNum = (value) => {
  const text = String(value ?? "").trim().replace("%", "");
  return num(text);
};
const mean = (xs) => xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
function quantile(xs, p) {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const h = (s.length - 1) * p;
  const lo = Math.floor(h);
  const hi = Math.ceil(h);
  return s[lo] + (s[hi] - s[lo]) * (h - lo);
}
const median = (xs) => quantile(xs, 0.5);
function sd(xs) {
  if (xs.length < 2) return null;
  const m = mean(xs);
  return Math.sqrt(xs.reduce((sum, x) => sum + (x - m) ** 2, 0) / (xs.length - 1));
}
const dayDiff = (later, earlier) => Math.round((later - earlier) / DAY_MS);
const share = (n, d) => d ? n / d : null;
function stats(xs) {
  const v = xs.filter(Number.isFinite);
  return {
    n: v.length,
    mean: mean(v),
    median: median(v),
    sd: sd(v),
    min: v.length ? Math.min(...v) : null,
    p05: quantile(v, 0.05),
    p25: quantile(v, 0.25),
    p75: quantile(v, 0.75),
    p95: quantile(v, 0.95),
    max: v.length ? Math.max(...v) : null,
  };
}

async function readCsv(file, sheetName) {
  const text = await fs.readFile(file, "utf8");
  const wb = await Workbook.fromCSV(text, { sheetName });
  const values = wb.worksheets.getItem(sheetName).getUsedRange().values;
  const headers = (values[0] ?? []).map((value) => String(value).replace(/^\uFEFF/, ""));
  const rows = values.slice(1).map((valuesRow) => Object.fromEntries(headers.map((header, index) => [header, valuesRow[index]])));
  return { text, headers, rows };
}

function genericAudit(spec, parsed, mandi) {
  const dateField = parsed.headers.includes("Time") ? "Time" : "Date";
  const closeField = parsed.headers.includes("Latest") ? "Latest" : "Price";
  const volumeField = parsed.headers.includes("Volume") ? "Volume" : "Vol.";
  const percentField = parsed.headers.includes("%Change") ? "%Change" : "Change %";
  const dataRows = parsed.rows.filter((row) => parseDate(row[dateField]));
  const nonDataRows = parsed.rows.filter((row) => !parseDate(row[dateField]));
  const originalDates = dataRows.map((row) => parseDate(row[dateField]));
  const rows = dataRows.map((row) => ({
    date: parseDate(row[dateField]),
    open: num(row.Open),
    high: num(row.High),
    low: num(row.Low),
    close: num(row[closeField]),
    change: parsed.headers.includes("Change") ? num(row.Change) : null,
    percentChange: pctNum(row[percentField]),
    volume: volumeNum(row[volumeField]),
    openInterest: parsed.headers.includes("Open Int") ? num(row["Open Int"]) : null,
  })).sort((a, b) => a.date - b.date);
  const dateCounts = new Map();
  rows.forEach((row) => dateCounts.set(iso(row.date), (dateCounts.get(iso(row.date)) ?? 0) + 1));
  const gaps = rows.slice(1).map((row, i) => dayDiff(row.date, rows[i].date));
  const validGaps = gaps.filter((gap) => gap > 0);
  const priceFields = ["open", "high", "low", "close"];
  const missing = Object.fromEntries(priceFields.map((field) => [field, rows.filter((row) => row[field] === null).length]));
  missing.volume = rows.filter((row) => row.volume === null).length;
  missing.openInterest = parsed.headers.includes("Open Int") ? rows.filter((row) => row.openInterest === null).length : null;
  missing.change = parsed.headers.includes("Change") ? rows.filter((row) => row.change === null).length : null;
  const ohlcComparable = rows.filter((row) => priceFields.every((field) => row[field] !== null));
  const ohlcViolations = ohlcComparable.filter((row) => row.high < Math.max(row.open, row.close) || row.low > Math.min(row.open, row.close));
  const returns = rows.slice(1).filter((row, i) => row.close !== null && rows[i].close !== null).map((row, i) => row.close / rows[i].close - 1);
  const changeMismatches = parsed.headers.includes("Change") ? rows.slice(1).filter((row, i) => row.change !== null && row.close !== null && rows[i].close !== null && Math.abs((row.close - rows[i].close) - row.change) > 1e-8).length : null;
  const percentMismatches = rows.filter((row, i) => {
    if (row.percentChange === null || row.close === null || i === 0) return false;
    const base = parsed.headers.includes("Change") && row.change !== null ? row.close - row.change : rows[i - 1].close;
    if (!base) return false;
    return Math.abs(100 * (row.close - base) / base - row.percentChange) > 0.011;
  }).length;
  const rowDateSet = new Set(rows.map((row) => iso(row.date)));
  const mandiWithinCoverage = rows.length ? mandi.filter((row) => row.date >= rows[0].date && row.date <= rows.at(-1).date) : [];
  function latestStrictPrior(date) {
    let lo = 0;
    let hi = rows.length - 1;
    let found = null;
    while (lo <= hi) {
      const mid = Math.floor((lo + hi) / 2);
      if (rows[mid].date < date) {
        found = rows[mid];
        lo = mid + 1;
      } else hi = mid - 1;
    }
    return found;
  }
  const strictAges = mandiWithinCoverage.map((row) => {
    const prior = latestStrictPrior(row.date);
    return prior ? dayDiff(row.date, prior.date) : null;
  }).filter(Number.isFinite);
  return {
    source_file: spec.file,
    identity: spec.identity,
    identity_confidence: spec.identityConfidence,
    venue: spec.venue,
    units: spec.units,
    verification_url: spec.verifiedUrl,
    model_relevance: spec.relevance,
    recommendation: spec.decision,
    schema: parsed.headers,
    raw_data_rows: parsed.rows.length,
    valid_dated_rows: rows.length,
    non_data_rows: nonDataRows.map((row) => row[dateField]).filter((value) => String(value ?? "").trim()),
    first_date: rows.length ? iso(rows[0].date) : null,
    last_date: rows.length ? iso(rows.at(-1).date) : null,
    original_order: originalDates.length < 2 ? "not_applicable" : originalDates[1] > originalDates[0] ? "ascending" : "descending",
    duplicate_dates: [...dateCounts].filter(([, count]) => count > 1).map(([date, count]) => ({ date, count })),
    median_calendar_gap_days: median(validGaps),
    p95_calendar_gap_days: quantile(validGaps, 0.95),
    inferred_frequency: !rows.length ? "empty" : median(validGaps) >= 6 ? "weekly" : "daily_or_business_daily",
    missingness: missing,
    price_min: rows.length ? Math.min(...rows.map((row) => row.close).filter(Number.isFinite)) : null,
    price_max: rows.length ? Math.max(...rows.map((row) => row.close).filter(Number.isFinite)) : null,
    zero_range_rows: ohlcComparable.filter((row) => row.high === row.low).length,
    zero_range_rate: share(ohlcComparable.filter((row) => row.high === row.low).length, ohlcComparable.length),
    ohlc_violations: ohlcViolations.length,
    ohlc_violation_examples: ohlcViolations.slice(0, 8).map((row) => ({ date: iso(row.date), open: row.open, high: row.high, low: row.low, close: row.close })),
    zero_volume_rows: rows.filter((row) => row.volume === 0).length,
    zero_volume_rate_among_reported: share(rows.filter((row) => row.volume === 0).length, rows.filter((row) => row.volume !== null).length),
    volume: stats(rows.map((row) => row.volume)),
    zero_open_interest_rows: parsed.headers.includes("Open Int") ? rows.filter((row) => row.openInterest === 0).length : null,
    zero_open_interest_rate: parsed.headers.includes("Open Int") ? share(rows.filter((row) => row.openInterest === 0).length, rows.length) : null,
    open_interest: parsed.headers.includes("Open Int") ? stats(rows.map((row) => row.openInterest)) : null,
    close_returns: stats(returns),
    close_return_zero_rate: share(returns.filter((value) => value === 0).length, returns.length),
    change_mismatches_vs_prior_row: changeMismatches,
    percent_change_mismatches: percentMismatches,
    strict_prior_date_alignment_to_mandi: {
      mandi_rows_within_file_coverage: mandiWithinCoverage.length,
      exact_same_date_matches_that_must_not_use_same_day_close: mandiWithinCoverage.filter((row) => rowDateSet.has(iso(row.date))).length,
      strict_prior_matches_within_coverage: strictAges.length,
      age_calendar_days: stats(strictAges),
      age_counts: Object.fromEntries([...new Set(strictAges)].sort((a, b) => a - b).map((age) => [age, strictAges.filter((value) => value === age).length])),
      rule: "Use the last source observation strictly earlier than the mandi date. Do not use same-date overseas closes. Respect the source's native frequency and expose observation age.",
    },
  };
}

function parseContract(symbol) {
  const match = String(symbol).match(/^IS7([FGHJKMNQUVXZ])(\d{2})$/);
  if (!match) return null;
  const month = monthCodes[match[1]];
  const year = 2000 + Number(match[2]);
  return { monthCode: match[1], month, year, serialMonth: year * 12 + month - 1 };
}
function monthEndUtc(year, month) {
  return new Date(Date.UTC(year, month, 0));
}

async function auditNearby() {
  const file = `${root}/research/inputs/turkey_scrap_daily_nearby.csv`;
  const parsed = await readCsv(file, "TurkeyNearby");
  const headers = parsed.headers;
  const sourceRows = parsed.rows;
  const nonDataRows = sourceRows.filter((row) => !parseDate(row.Time));
  const rows = sourceRows.filter((row) => parseDate(row.Time)).map((row) => ({
    symbol: String(row.Symbol),
    date: parseDate(row.Time),
    open: num(row.Open),
    high: num(row.High),
    low: num(row.Low),
    close: num(row.Latest),
    change: num(row.Change),
    percentChange: pctNum(row["%Change"]),
    volume: num(row.Volume),
    openInterest: num(row["Open Int"]),
  })).sort((a, b) => a.date - b.date);

  const rollRecords = [];
  const segments = [];
  let cumulativeRollBasis = 0;
  let returnIndex = 100;
  let segmentStart = 0;
  rows[0].rawReturn = null;
  rows[0].reportedReturn = null;
  rows[0].isRoll = false;
  rows[0].cumulativeRollBasis = 0;
  rows[0].pointInTimeAdjustedClose = rows[0].close;
  rows[0].returnIndex = returnIndex;

  for (let i = 1; i < rows.length; i++) {
    const row = rows[i];
    const prior = rows[i - 1];
    const isRoll = row.symbol !== prior.symbol;
    const impliedPriorReferenceClose = row.close - row.change;
    const reportedReturn = impliedPriorReferenceClose ? row.close / impliedPriorReferenceClose - 1 : null;
    row.rawReturn = row.close / prior.close - 1;
    row.reportedReturn = reportedReturn;
    row.isRoll = isRoll;
    if (isRoll) {
      const outgoing = parseContract(prior.symbol);
      const incoming = parseContract(row.symbol);
      const basis = impliedPriorReferenceClose - prior.close;
      cumulativeRollBasis += basis;
      const outgoingMonthEnd = outgoing ? monthEndUtc(outgoing.year, outgoing.month) : null;
      rollRecords.push({
        roll_date: iso(row.date),
        prior_date: iso(prior.date),
        outgoing_symbol: prior.symbol,
        incoming_symbol: row.symbol,
        outgoing_close: prior.close,
        incoming_close: row.close,
        incoming_reported_change: row.change,
        incoming_implied_prior_reference_close: impliedPriorReferenceClose,
        naive_switch_gap: row.close - prior.close,
        observable_vendor_roll_adjustment: basis,
        observable_vendor_roll_adjustment_pct_of_outgoing: basis / prior.close,
        naive_cross_contract_return: row.rawReturn,
        vendor_reported_return: reportedReturn,
        cumulative_observable_vendor_adjustment_after_switch: cumulativeRollBasis,
        incoming_volume: row.volume,
        incoming_open_interest: row.openInterest,
        incoming_zero_range: row.high === row.low,
        calendar_gap_from_prior_row: dayDiff(row.date, prior.date),
        contract_month_step: outgoing && incoming ? incoming.serialMonth - outgoing.serialMonth : null,
        calendar_days_before_outgoing_month_end: outgoingMonthEnd ? dayDiff(outgoingMonthEnd, row.date) : null,
      });
      const segmentRows = rows.slice(segmentStart, i);
      segments.push(summarizeSegment(segmentRows));
      segmentStart = i;
    }
    row.cumulativeRollBasis = cumulativeRollBasis;
    row.pointInTimeAdjustedClose = row.close - cumulativeRollBasis;
    if (reportedReturn !== null) returnIndex *= 1 + reportedReturn;
    row.returnIndex = returnIndex;
  }
  segments.push(summarizeSegment(rows.slice(segmentStart)));

  const nonRollMismatches = rows.slice(1).filter((row, index) => !row.isRoll && Math.abs((row.close - rows[index].close) - row.change) > 1e-8);
  const rollNaiveMismatch = rollRecords.filter((roll) => Math.abs(roll.naive_switch_gap - roll.incoming_reported_change) > 1e-8);
  const percentMismatches = rows.filter((row) => {
    const base = row.close - row.change;
    return base && Math.abs(100 * row.change / base - row.percentChange) > 0.011;
  });
  const duplicateDates = [];
  const dateCounts = new Map();
  rows.forEach((row) => dateCounts.set(iso(row.date), (dateCounts.get(iso(row.date)) ?? 0) + 1));
  for (const [date, count] of dateCounts) if (count > 1) duplicateDates.push({ date, count });
  const calendarGaps = rows.slice(1).map((row, index) => ({
    prior_date: iso(rows[index].date),
    next_date: iso(row.date),
    calendar_days: dayDiff(row.date, rows[index].date),
  })).filter((gap) => gap.calendar_days > 5).sort((a, b) => b.calendar_days - a.calendar_days);
  const ohlcViolations = rows.filter((row) => row.high < Math.max(row.open, row.close) || row.low > Math.min(row.open, row.close));
  const allRawReturns = rows.slice(1).map((row) => row.rawReturn);
  const allReportedReturns = rows.slice(1).map((row) => row.reportedReturn);
  const rollExcludedIndexEnd = 100 * Math.exp(rows.slice(1).filter((row) => !row.isRoll).reduce((sum, row) => sum + Math.log1p(row.rawReturn), 0));
  const observableRollAdjustment = rollRecords.map((roll) => roll.observable_vendor_roll_adjustment);
  const switchGaps = rollRecords.map((roll) => roll.naive_switch_gap);
  const volumeConcentration = [...rows].sort((a, b) => b.volume - a.volume);
  const totalVolume = rows.reduce((sum, row) => sum + row.volume, 0);
  const topVolume = (n) => share(volumeConcentration.slice(0, n).reduce((sum, row) => sum + row.volume, 0), totalVolume);

  const mandiParsed = await readCsv(`${root}/research/inputs/mandi_master.csv`, "Mandi");
  const mandi = mandiParsed.rows.filter((row) => parseDate(row.Date)).map((row) => ({ date: parseDate(row.Date), eightAni: num(row["8ANI"]) })).sort((a, b) => a.date - b.date);
  const dateSet = new Set(rows.map((row) => iso(row.date)));
  function latestStrictPrior(date) {
    let lo = 0;
    let hi = rows.length - 1;
    let found = null;
    while (lo <= hi) {
      const mid = Math.floor((lo + hi) / 2);
      if (rows[mid].date < date) {
        found = rows[mid];
        lo = mid + 1;
      } else hi = mid - 1;
    }
    return found;
  }
  const aligned = mandi.map((row) => {
    const prior = latestStrictPrior(row.date);
    return { mandiDate: row.date, prior, age: prior ? dayDiff(row.date, prior.date) : null };
  });
  const ages = aligned.map((item) => item.age).filter(Number.isFinite);
  const rollDateSet = new Set(rollRecords.map((roll) => roll.roll_date));

  return {
    source_file: file,
    identity: "Barchart daily-nearby/continuous LME Steel Scrap CFR Turkey (Platts) benchmark, with underlying contract in Symbol",
    schema: headers,
    raw_data_rows: sourceRows.length,
    valid_dated_rows: rows.length,
    non_data_rows: nonDataRows.map((row) => row.Time),
    first_date: iso(rows[0].date),
    last_date: iso(rows.at(-1).date),
    duplicate_dates: duplicateDates,
    contract_count: new Set(rows.map((row) => row.symbol)).size,
    roll_count: rollRecords.length,
    contract_symbols: [...new Set(rows.map((row) => row.symbol))],
    skipped_contract_months: rollRecords.filter((roll) => roll.contract_month_step !== 1).map((roll) => ({ roll_date: roll.roll_date, outgoing_symbol: roll.outgoing_symbol, incoming_symbol: roll.incoming_symbol, contract_month_step: roll.contract_month_step })),
    integrity: {
      missing_values: Object.fromEntries(["open", "high", "low", "close", "change", "percentChange", "volume", "openInterest"].map((field) => [field, rows.filter((row) => row[field] === null).length])),
      nonroll_change_mismatches: nonRollMismatches.length,
      roll_rows_where_naive_gap_differs_from_reported_change: rollNaiveMismatch.length,
      roll_rows_where_reported_change_equals_naive_gap: rollRecords.length - rollNaiveMismatch.length,
      percent_change_mismatches: percentMismatches.length,
      ohlc_violations: ohlcViolations.length,
      ohlc_violation_examples: ohlcViolations.map((row) => ({ date: iso(row.date), symbol: row.symbol, open: row.open, high: row.high, low: row.low, close: row.close, volume: row.volume })),
      calendar_gaps_over_5_days: calendarGaps,
      critical_gap_note: calendarGaps.length ? "The 2024-08-19 to 2024-09-25 discontinuity leaves no daily-nearby observations for more than a month and produces 30-36-day stale strict-prior matches in the mandi panel." : null,
    },
    settlement_and_liquidity_quality: {
      zero_volume_rows: rows.filter((row) => row.volume === 0).length,
      zero_volume_rate: share(rows.filter((row) => row.volume === 0).length, rows.length),
      zero_open_interest_rows: rows.filter((row) => row.openInterest === 0).length,
      zero_open_interest_rate: share(rows.filter((row) => row.openInterest === 0).length, rows.length),
      zero_range_rows: rows.filter((row) => row.high === row.low).length,
      zero_range_rate: share(rows.filter((row) => row.high === row.low).length, rows.length),
      changed_close_despite_zero_volume_rows: rows.slice(1).filter((row) => row.volume === 0 && row.change !== 0).length,
      roll_rows_zero_volume: rollRecords.filter((roll) => roll.incoming_volume === 0).length,
      roll_rows_zero_range: rollRecords.filter((roll) => roll.incoming_zero_range).length,
      roll_rows_zero_open_interest: rollRecords.filter((roll) => roll.incoming_open_interest === 0).length,
      total_volume: totalVolume,
      top_1_day_volume_share: topVolume(1),
      top_5_days_volume_share: topVolume(5),
      top_10_days_volume_share: topVolume(10),
      volume: stats(rows.map((row) => row.volume)),
      open_interest: stats(rows.map((row) => row.openInterest)),
      warning: "Most closes are LME settlement/curve marks. Zero volume does not imply a missing close; it does imply that the close may come from the LME pricing waterfall rather than a pricing-window VWAP.",
    },
    roll_adjustment: {
      derivation_and_identification_test: {
        implied_prior_reference_close: "Latest_t - Change_t",
        observable_vendor_roll_adjustment: "(Latest_t - Change_t) - Latest_(t-1,outgoing)",
        switch_gap_identity: "Latest_t - Latest_(t-1,outgoing) = Change_t + observable_vendor_roll_adjustment",
        empirical_result: "The observable vendor roll adjustment equals exactly zero at all 42 switches. Therefore Barchart Change references the outgoing nearby close and reproduces the cross-contract switch gap; it is not a roll-neutral same-contract return.",
        identification_limit: "The true incoming-minus-outgoing contract basis is not identifiable from this file. It requires overlapping closes for both contracts on the same pre-roll date or an independently documented continuous-series adjustment.",
        safe_point_in_time_treatment: "Set roll-day return to missing and add a roll flag until overlapping contract closes are acquired. Any later back-adjustment must use only bases observed by that historical date.",
        availability: "Even with overlapping contracts, a basis observed on roll date r may first enter an Indian mandi feature for d > r.",
      },
      observable_vendor_roll_adjustment_usd_per_tonne: stats(observableRollAdjustment),
      raw_cross_contract_switch_gap_usd_per_tonne: stats(switchGaps),
      raw_cross_contract_switch_gap_pct_of_outgoing: stats(switchGaps.map((gap, i) => gap / rollRecords[i].outgoing_close)),
      switch_gaps_over_2pct_count: rollRecords.filter((roll) => Math.abs(roll.naive_cross_contract_return) > 0.02).length,
      switch_gaps_over_3pct_count: rollRecords.filter((roll) => Math.abs(roll.naive_cross_contract_return) > 0.03).length,
      switch_gaps_over_5pct_count: rollRecords.filter((roll) => Math.abs(roll.naive_cross_contract_return) > 0.05).length,
      top_15_absolute_raw_returns_roll_count: [...rows.slice(1)].sort((a, b) => Math.abs(b.rawReturn) - Math.abs(a.rawReturn)).slice(0, 15).filter((row) => row.isRoll).length,
      observable_adjustment_positive_count: observableRollAdjustment.filter((value) => value > 0).length,
      observable_adjustment_negative_count: observableRollAdjustment.filter((value) => value < 0).length,
      observable_adjustment_zero_count: observableRollAdjustment.filter((value) => value === 0).length,
      cumulative_observable_vendor_adjustment_end: cumulativeRollBasis,
      raw_start_close: rows[0].close,
      raw_end_close: rows.at(-1).close,
      no_op_observable_adjusted_end_close: rows.at(-1).pointInTimeAdjustedClose,
      vendor_change_linked_index_start: 100,
      vendor_change_linked_index_end: rows.at(-1).returnIndex,
      roll_excluded_diagnostic_index_end: rollExcludedIndexEnd,
      raw_close_total_return: rows.at(-1).close / rows[0].close - 1,
      vendor_change_linked_total_return: rows.at(-1).returnIndex / 100 - 1,
      roll_excluded_diagnostic_total_return: rollExcludedIndexEnd / 100 - 1,
      roll_excluded_diagnostic_warning: "This index merely holds flat across all 42 switches. It avoids switch-gap contamination but also discards any genuine market move occurring on roll dates; use it only as a sensitivity diagnostic, not as a fully identified continuous futures return.",
      volatility: {
        raw_all_row_log_return_sd: sd(allRawReturns.map((value) => Math.log1p(value))),
        vendor_change_log_return_sd: sd(allReportedReturns.map((value) => Math.log1p(value))),
        raw_nonroll_log_return_sd: sd(rows.slice(1).filter((row) => !row.isRoll).map((row) => Math.log1p(row.rawReturn))),
        raw_roll_log_return_sd: sd(rows.filter((row) => row.isRoll).map((row) => Math.log1p(row.rawReturn))),
        vendor_change_roll_day_log_return_sd: sd(rows.filter((row) => row.isRoll).map((row) => Math.log1p(row.reportedReturn))),
      },
      roll_timing_calendar_days_before_outgoing_month_end: stats(rollRecords.map((roll) => roll.calendar_days_before_outgoing_month_end)),
      largest_absolute_raw_switch_gaps: [...rollRecords].sort((a, b) => Math.abs(b.naive_switch_gap) - Math.abs(a.naive_switch_gap)).slice(0, 12),
      roll_table: rollRecords,
    },
    contract_segments: segments,
    strict_prior_date_alignment_to_mandi: {
      mandi_rows: mandi.length,
      exact_same_date_matches_that_must_not_use_same_day_close: mandi.filter((row) => dateSet.has(iso(row.date))).length,
      strict_prior_matches: ages.length,
      age_calendar_days: stats(ages),
      age_counts: Object.fromEntries([...new Set(ages)].sort((a, b) => a - b).map((age) => [age, ages.filter((value) => value === age).length])),
      matches_with_age_at_most_3_days: ages.filter((age) => age <= 3).length,
      matches_with_age_at_most_4_days: ages.filter((age) => age <= 4).length,
      mandi_dates_that_are_roll_dates: mandi.filter((row) => rollDateSet.has(iso(row.date))).length,
      rule: "For mandi date d, use the most recent Turkey row with Time < d. Never use Time = d because the LME final close is published around 17:50 London, after the Indian business day. A roll adjustment learned on roll date r may first enter a mandi feature for d > r.",
    },
  };
}

function summarizeSegment(rows) {
  return {
    symbol: rows[0]?.symbol ?? null,
    first_date: rows.length ? iso(rows[0].date) : null,
    last_date: rows.length ? iso(rows.at(-1).date) : null,
    rows: rows.length,
    calendar_days: rows.length ? dayDiff(rows.at(-1).date, rows[0].date) + 1 : 0,
    first_close: rows[0]?.close ?? null,
    last_close: rows.at(-1)?.close ?? null,
    total_volume: rows.reduce((sum, row) => sum + row.volume, 0),
    zero_volume_rate: share(rows.filter((row) => row.volume === 0).length, rows.length),
    zero_range_rate: share(rows.filter((row) => row.high === row.low).length, rows.length),
    median_open_interest: median(rows.map((row) => row.openInterest)),
    max_open_interest: rows.length ? Math.max(...rows.map((row) => row.openInterest)) : null,
  };
}

const turkeyNearby = await auditNearby();
const mandiForExternalParsed = await readCsv(`${root}/research/inputs/mandi_master.csv`, "MandiExternal");
const mandiForExternal = mandiForExternalParsed.rows.filter((row) => parseDate(row.Date)).map((row) => ({ date: parseDate(row.Date) })).sort((a, b) => a.date - b.date);
const externalFiles = {};
for (const spec of sourceSpecs) {
  const parsed = await readCsv(spec.file, spec.key.replace(/[^a-z0-9]/gi, "_").slice(0, 28));
  externalFiles[spec.key] = genericAudit(spec, parsed, mandiForExternal);
}

const report = {
  generated_at_utc: new Date().toISOString(),
  scope: "Point-in-time audit of the Barchart Turkey daily-nearby series plus relevant downloaded FX and ferrous market CSVs",
  turkey_daily_nearby: turkeyNearby,
  external_market_files: externalFiles,
  recommendations: [
    "Do not use either Change or raw close differences on Turkey roll dates: Change equals the raw cross-symbol gap at all 42 switches, so it does not remove contract basis.",
    "The Symbol-and-Change identification test produces zero observable vendor adjustment at every switch. True roll basis requires overlapping outgoing and incoming contract closes; until then set roll-day returns to missing and carry an explicit roll flag.",
    "If overlapping contracts are acquired, maintain a causal return-linked index or forward-adjusted close. Do not globally back-adjust history using roll bases that were not yet observable.",
    "Merge every overseas feature to mandi using a strict prior-date as-of join; same-date LME closes are look-ahead for India.",
    "Retain zero-volume LME closes as settlement/curve marks with quality flags, but do not call them executable transaction prices.",
    "Use Turkey rebar minus Turkey scrap only when contract prompt months match; otherwise curve slope contaminates the margin spread.",
    "Obtain longer USD/INR history before using INR-converted imported scrap levels in backtests.",
    "Use only the Price column of the Investing.com HRC history at its native weekly frequency: 89 of 147 rows have Price outside the reported OHLC range and 35 volumes are missing. Its continuous-roll method is undocumented, so do not infer daily contract returns or roll bases from it.",
    "TRQ26 contains 519 rows but every row has zero volume, zero OI, and zero range. It is a settlement/assessment curve, not tradable return history; exclude its returns from the primary model.",
    "Fixed YQU26, V7Q26, TRQ26, and R-U26 files are short or maturity-dependent. Treat them as current-regime/curve observations until continuous point-in-time histories are acquired.",
  ],
  source_documentation: {
    lme_cash_settled_futures_methodology: "https://www.lme.com/-/media/Files/About/Regulation/Key-compliance-notices/CashSettled-Futures-Daily-Settlement-Prices-Methodology.pdf",
    lme_historical_forward_curves: "https://www.lme.com/en/market-data/reports-and-data/historical-data-for-cash-settled-futures",
  },
};

await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(JSON.stringify({ outputPath, nearby: { rows: turkeyNearby.valid_dated_rows, rolls: turkeyNearby.roll_count }, external: Object.fromEntries(Object.entries(externalFiles).map(([key, value]) => [key, { rows: value.valid_dated_rows, first: value.first_date, last: value.last_date, recommendation: value.recommendation }])) }, null, 2));
