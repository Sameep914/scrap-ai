"use strict";

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const INPUT = path.join(ROOT, "research", "inputs");
const OUTPUT = path.join(ROOT, "research", "outputs", "turkey_edge_test");
fs.mkdirSync(OUTPUT, { recursive: true });

const HORIZONS = [5, 10, 15, 30, 45, 60, 90];
const SIGNALS = ["mom5", "mom10", "mom20", "rv10"];
const VERSIONS = ["roll_safe_v2", "overlap_adjusted_v3"];
const FEATURES = ["turkey_mom5", "turkey_mom10", "turkey_mom20", "turkey_rv10"];
const ALPHAS = [1, 10, 100];
const MIN_TRAIN = 80;
const SPACING_DAYS = 7;
const STALE_DAYS = 4;
const BOOT_REPS = 2000;
const NULL_REPS = 2000;
const SEED = 20260812;
const DAY = 86400000;

function parseCsv(text) {
  const rows = [];
  let row = [], field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { row.push(field); field = ""; }
    else if (c === '\n') { row.push(field.replace(/\r$/, "")); rows.push(row); row = []; field = ""; }
    else field += c;
  }
  if (field.length || row.length) { row.push(field.replace(/\r$/, "")); rows.push(row); }
  const header = rows.shift();
  return rows.filter(r => r.length > 1).map(r => Object.fromEntries(header.map((h, i) => [h, r[i] ?? ""])));
}

function csv(rows) {
  if (!rows.length) return "";
  const keys = Object.keys(rows[0]);
  const esc = v => {
    if (v === null || v === undefined || Number.isNaN(v)) return "";
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
  };
  return keys.join(",") + "\n" + rows.map(r => keys.map(k => esc(r[k])).join(",")).join("\n") + "\n";
}

function num(v) { const x = Number(String(v ?? "").replaceAll(",", "").replace("%", "")); return Number.isFinite(x) ? x : NaN; }
function dateMs(v) { const t = Date.parse(`${v}T00:00:00Z`); return Number.isFinite(t) ? t : NaN; }
function dateStr(t) { return new Date(t).toISOString().slice(0, 10); }
function mean(a) { return a.reduce((s, x) => s + x, 0) / a.length; }
function quantile(values, p) {
  const a = [...values].sort((x, y) => x - y); if (!a.length) return NaN;
  const q = (a.length - 1) * p, lo = Math.floor(q), hi = Math.ceil(q);
  return a[lo] + (a[hi] - a[lo]) * (q - lo);
}
function sd(a) { if (a.length < 2) return NaN; const m = mean(a); return Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / (a.length - 1)); }
function median(a) { return quantile(a, 0.5); }

let state = SEED >>> 0;
function rand() { state += 0x6D2B79F5; let t = state; t = Math.imul(t ^ t >>> 15, t | 1); t ^= t + Math.imul(t ^ t >>> 7, t | 61); return ((t ^ t >>> 14) >>> 0) / 4294967296; }
function randint(n) { return Math.floor(rand() * n); }

function invert(A) {
  const n = A.length, M = A.map((r, i) => [...r, ...Array.from({length:n}, (_,j)=>i===j?1:0)]);
  for (let c = 0; c < n; c++) {
    let p = c; for (let r=c+1;r<n;r++) if (Math.abs(M[r][c])>Math.abs(M[p][c])) p=r;
    if (Math.abs(M[p][c]) < 1e-12) return null;
    [M[c],M[p]]=[M[p],M[c]]; const d=M[c][c]; for(let j=0;j<2*n;j++) M[c][j]/=d;
    for(let r=0;r<n;r++) if(r!==c){const f=M[r][c];for(let j=0;j<2*n;j++)M[r][j]-=f*M[c][j];}
  }
  return M.map(r=>r.slice(n));
}
function ridgeFit(X, Y, alpha) {
  const D = X.map(r => [1, ...r]), p = D[0].length, k = Array.isArray(Y[0]) ? Y[0].length : 1;
  const XtX = Array.from({length:p},()=>Array(p).fill(0)), XtY = Array.from({length:p},()=>Array(k).fill(0));
  for(let i=0;i<D.length;i++) for(let a=0;a<p;a++) { for(let b=0;b<p;b++) XtX[a][b]+=D[i][a]*D[i][b]; for(let j=0;j<k;j++) XtY[a][j]+=D[i][a]*(k===1?Y[i]:Y[i][j]); }
  for(let a=1;a<p;a++) XtX[a][a]+=alpha;
  const inv=invert(XtX); if(!inv) throw new Error("singular");
  return inv.map(r=>Array.from({length:k},(_,j)=>r.reduce((s,v,i)=>s+v*XtY[i][j],0)));
}
function ridgePredict(beta, X) { return X.map(r => { const d=[1,...r]; return beta[0].map((_,j)=>d.reduce((s,v,i)=>s+v*beta[i][j],0)); }); }

function fitPrep(rows, names) {
  return names.map(name => { const a=rows.map(r=>r[name]).filter(Number.isFinite); const med=median(a), lo=quantile(a,.01), hi=quantile(a,.99); const c=a.map(x=>Math.max(lo,Math.min(hi,x))); return {name,med,lo,hi,m:mean(c),s:sd(c)||1}; });
}
function prep(rows, P) { return rows.map(r=>P.map(p=>(Math.max(p.lo,Math.min(p.hi,Number.isFinite(r[p.name])?r[p.name]:p.med))-p.m)/p.s)); }
function probs(raw, freq) { const a=raw.map((v,i)=>Math.max(0,v)+.15*freq[i]); const s=a.reduce((x,y)=>x+y,0); return a.map(v=>v/s); }
function onehot(c) { const a=[0,0,0]; a[c+1]=1; return a; }
function brier(c,p) { const y=onehot(c); return y.reduce((s,v,i)=>s+(v-p[i])**2,0); }

function loadData() {
  const mandi=parseCsv(fs.readFileSync(path.join(INPUT,"mandi_master.csv"),"utf8")).map(r=>({date:dateMs(r.Date),price:num(r["8ANI"])})).filter(r=>Number.isFinite(r.date)&&r.price>0).sort((a,b)=>a.date-b.date);
  const adjusted=parseCsv(fs.readFileSync(path.join(INPUT,"turkey_scrap_overlap_adjusted.csv"),"utf8")).map(r=>({
    date:dateMs(r.date), symbol:r.Symbol, latest:num(r.Latest), oi:num(r["Open Int"]), high:num(r.High), low:num(r.Low),
    ret:num(r.overlap_adjusted_log_return), turkey_mom5:num(r.turkey_mom5), turkey_mom10:num(r.turkey_mom10), turkey_mom20:num(r.turkey_mom20), turkey_rv10:num(r.turkey_rv10)
  })).filter(r=>Number.isFinite(r.date)).sort((a,b)=>a.date-b.date);
  const nearby=parseCsv(fs.readFileSync(path.join(INPUT,"turkey_scrap_daily_nearby.csv"),"utf8")).map(r=>({date:dateMs(r.Time),symbol:r.Symbol,latest:num(r.Latest),oi:num(r["Open Int"]),high:num(r.High),low:num(r.Low)})).filter(r=>Number.isFinite(r.date)).sort((a,b)=>a.date-b.date);
  for(let i=0;i<nearby.length;i++){
    const same=i>0&&nearby[i].symbol===nearby[i-1].symbol;
    nearby[i].ret=same?Math.log(nearby[i].latest/nearby[i-1].latest):NaN;
    for(const n of [5,10,20]) nearby[i][`turkey_mom${n}`]=i>=n&&nearby[i-n].symbol===nearby[i].symbol?Math.log(nearby[i].latest/nearby[i-n].latest):NaN;
    const prior=[]; for(let j=Math.max(0,i-10);j<i;j++) if(Number.isFinite(nearby[j].ret)&&nearby[j].symbol===nearby[i].symbol) prior.push(nearby[j].ret);
    nearby[i].turkey_rv10=prior.length>=7?sd(prior):NaN;
  }
  return {mandi, series:{roll_safe_v2:nearby,overlap_adjusted_v3:adjusted}};
}

function buildPanel(mandi, turkey, H) {
  const out=[]; let j=-1;
  for(let i=0;i<mandi.length;i++){
    const m=mandi[i]; while(j+1<turkey.length&&turkey[j+1].date<m.date)j++;
    if(j<0)continue; const t=turkey[j],age=(m.date-t.date)/DAY;
    let e=i; while(e<mandi.length&&mandi[e].date<m.date+H*DAY)e++;
    if(e>=mandi.length)continue; const elapsed=(mandi[e].date-m.date)/DAY; if(elapsed>H+4)continue;
    out.push({date:m.date,targetEnd:mandi[e].date,y:Math.log(mandi[e].price/m.price),cls:mandi[e].price>m.price?1:mandi[e].price<m.price?-1:0,price:m.price,turkeyDate:t.date,age,symbol:t.symbol,quality:age<=STALE_DAYS&&t.oi>0&&t.latest>0,...Object.fromEntries(FEATURES.map(k=>[k,t[k]]))});
  }
  return out;
}

function chooseAlpha(train, names, task) {
  if(train.length<100)return 10; const cut=Math.floor(train.length*.8), tr=train.slice(0,cut), va=train.slice(cut); if(va.length<10)return 10;
  const P=fitPrep(tr,names), X=prep(tr,P), V=prep(va,P), counts=[-1,0,1].map(c=>tr.filter(r=>r.cls===c).length),freq=counts.map(c=>(c+1)/(tr.length+3));
  let best={loss:Infinity,alpha:10};
  for(const alpha of ALPHAS){let loss;if(task==="magnitude"){const b=ridgeFit(X,tr.map(r=>r.y),alpha);const pr=ridgePredict(b,V).map(x=>x[0]);loss=mean(pr.map((p,i)=>Math.abs(va[i].y-p)));}else{const b=ridgeFit(X,tr.map(r=>onehot(r.cls)),alpha);const pr=ridgePredict(b,V).map(x=>probs(x,freq));loss=mean(pr.map((p,i)=>brier(va[i].cls,p)));} if(loss<best.loss-.0000001||Math.abs(loss-best.loss)<=best.loss*.01&&alpha>best.alpha)best={loss,alpha};}
  return best.alpha;
}

function testVersion(mandi, turkey, version, H, names) {
  const panel=buildPanel(mandi,turkey,H).filter(r=>r.quality&&names.every(k=>Number.isFinite(r[k])));
  const rows=[]; let last=-Infinity;
  for(let i=0;i<panel.length;i++){
    const o=panel[i]; const train=panel.filter(r=>r.targetEnd<o.date);
    if(train.length<MIN_TRAIN||o.date-last<SPACING_DAYS*DAY)continue;
    const P=fitPrep(train,names),X=prep(train,P),xt=prep([o],P),aMag=chooseAlpha(train,names,"magnitude"),aDir=chooseAlpha(train,names,"direction");
    const mag=ridgePredict(ridgeFit(X,train.map(r=>r.y),aMag),xt)[0][0];
    const counts=[-1,0,1].map(c=>train.filter(r=>r.cls===c).length),freq=counts.map(c=>(c+1)/(train.length+3));
    const p=probs(ridgePredict(ridgeFit(X,train.map(r=>onehot(r.cls)),aDir),xt)[0],freq);
    rows.push({version,horizon:H,signal:names.length===1?names[0].replace("turkey_",""):"all4",origin_date:dateStr(o.date),target_end:dateStr(o.targetEnd),actual:o.y,pred:mag,actual_class:o.cls,p_down:p[0],p_flat:p[1],p_up:p[2],f_down:freq[0],f_flat:freq[1],f_up:freq[2],pred_class:p.indexOf(Math.max(...p))-1,majority:freq.indexOf(Math.max(...freq))-1,turkey_date:dateStr(o.turkeyDate),turkey_age:o.age});
    last=o.date;
  }
  return rows;
}

function greedy(rows){const out=[];let end=-Infinity;for(const r of rows){const d=dateMs(r.origin_date);if(d>=end){out.push(r);end=dateMs(r.target_end);}}return out;}
function blocks(n,b){const idx=[];while(idx.length<n){const s=randint(n);for(let j=0;j<b&&idx.length<n;j++)idx.push((s+j)%n);}return idx;}
function ci(values,b){const m=[];for(let k=0;k<BOOT_REPS;k++){const ix=blocks(values.length,b);m.push(mean(ix.map(i=>values[i])));}return [quantile(m,.025),quantile(m,.975),sd(m)];}

function summarize(rows){
  const y=rows.map(r=>r.actual),e=rows.map(r=>Math.abs(r.actual)-Math.abs(r.actual-r.pred)),bd=rows.map(r=>brier(r.actual_class,[r.f_down,r.f_flat,r.f_up])-brier(r.actual_class,[r.p_down,r.p_flat,r.p_up]));
  const H=rows[0].horizon,b=Math.max(3,Math.min(Math.round(H/7),Math.floor(rows.length/3))), independent=greedy(rows); const mc=ci(e,b),bc=ci(bd,b);
  const thirds=[0,1,2].map(q=>e.slice(Math.floor(q*e.length/3),Math.floor((q+1)*e.length/3))).filter(a=>a.length).map(mean);
  const phases=new Map();for(const r of rows){const ph=Math.floor((dateMs(r.origin_date)-dateMs("2000-01-01"))/DAY)%H;if(!phases.has(ph))phases.set(ph,[]);phases.get(ph).push(r);}
  const ps=[...phases.values()].map(g=>greedy(g)).filter(g=>g.length>=2).map(g=>mean(g.map(r=>Math.abs(r.actual)-Math.abs(r.actual-r.pred))));
  return {version:rows[0].version,horizon:H,signal:rows[0].signal,raw_oos_n:rows.length,independent_n:independent.length,mae_skill_log:mean(e),mae_skill_pct:mean(e)/mean(y.map(Math.abs)),mae_ci_low:mc[0],mae_ci_high:mc[1],brier_skill:mean(bd),brier_ci_low:bc[0],brier_ci_high:bc[1],accuracy:mean(rows.map(r=>r.pred_class===r.actual_class?1:0)),majority_accuracy:mean(rows.map(r=>r.majority===r.actual_class?1:0)),third_skill_min:Math.min(...thirds),phase_positive_share:ps.length?mean(ps.map(x=>x>0?1:0)):NaN,phase_count:ps.length};
}

function maxNull(summaries, allRows, metric){
  const candidates=summaries.map(s=>{const rs=allRows.filter(r=>r.version===s.version&&r.horizon===s.horizon&&r.signal===s.signal),v=metric==="mae"?rs.map(r=>Math.abs(r.actual)-Math.abs(r.actual-r.pred)):rs.map(r=>brier(r.actual_class,[r.f_down,r.f_flat,r.f_up])-brier(r.actual_class,[r.p_down,r.p_flat,r.p_up]));const m=mean(v),se=sd(v)/Math.sqrt(v.length);return {s,v,m,se};});
  const maxima=[];for(let k=0;k<NULL_REPS;k++){let mx=-Infinity;for(const c of candidates){const centered=c.v.map(x=>x-c.m),b=Math.max(3,Math.min(Math.round(c.s.horizon/7),Math.floor(centered.length/3))),ix=blocks(centered.length,b),z=mean(ix.map(i=>centered[i]))/(c.se||1);mx=Math.max(mx,z);}maxima.push(mx);}
  for(const c of candidates){const z=c.m/(c.se||1);c.s[`${metric}_adj_p`]=(1+maxima.filter(x=>x>=z).length)/(NULL_REPS+1);}
}

function live(series,names){const last=series[series.length-1];const vals=names.map(n=>last[n]);return {date:dateStr(last.date),symbol:last.symbol,latest:last.latest,...Object.fromEntries(names.map((n,i)=>[n,vals[i]]))};}

function liveForecast(mandi, turkey, version, H, names) {
  const origin = mandi[mandi.length - 1];
  let t = null;
  for (const row of turkey) if (row.date < origin.date) t = row; else break;
  if (!t) return null;
  const liveRow = {
    date: origin.date, price: origin.price, turkeyDate: t.date,
    age: (origin.date - t.date) / DAY, symbol: t.symbol,
    quality: (origin.date - t.date) / DAY <= STALE_DAYS && t.oi > 0 && t.latest > 0,
    ...Object.fromEntries(FEATURES.map(k => [k, t[k]])),
  };
  if (!liveRow.quality || !names.every(k => Number.isFinite(liveRow[k]))) return null;
  const train = buildPanel(mandi, turkey, H)
    .filter(r => r.quality && r.targetEnd < origin.date && names.every(k => Number.isFinite(r[k])));
  if (train.length < MIN_TRAIN) return null;
  const P = fitPrep(train, names), X = prep(train, P), xt = prep([liveRow], P);
  const aMag = chooseAlpha(train, names, "magnitude"), aDir = chooseAlpha(train, names, "direction");
  const pred = ridgePredict(ridgeFit(X, train.map(r => r.y), aMag), xt)[0][0];
  const counts = [-1, 0, 1].map(c => train.filter(r => r.cls === c).length);
  const freq = counts.map(c => (c + 1) / (train.length + 3));
  const p = probs(ridgePredict(ridgeFit(X, train.map(r => onehot(r.cls)), aDir), xt)[0], freq);
  return {
    version, horizon: H, signal: names.length === 1 ? names[0].replace("turkey_", "") : "all4",
    origin_date: dateStr(origin.date), current_8ani: origin.price,
    turkey_date: dateStr(t.date), turkey_age: liveRow.age, turkey_symbol: t.symbol,
    train_raw_n: train.length, predicted_log_return: pred,
    predicted_pct: 100 * (Math.exp(pred) - 1), predicted_price: origin.price * Math.exp(pred),
    prob_down: p[0], prob_flat: p[1], prob_up: p[2], predicted_class: p.indexOf(Math.max(...p)) - 1,
    alpha_magnitude: aMag, alpha_direction: aDir,
    ...Object.fromEntries(names.map(n => [n, liveRow[n]])),
  };
}

function main(){
  const {mandi,series}=loadData(),all=[];
  for(const version of VERSIONS)for(const H of HORIZONS)for(const names of [...SIGNALS.map(s=>[`turkey_${s}`]),FEATURES])all.push(...testVersion(mandi,series[version],version,H,names));
  const groups=new Map();for(const r of all){const k=[r.version,r.horizon,r.signal].join("|");if(!groups.has(k))groups.set(k,[]);groups.get(k).push(r);}
  const summaries=[...groups.values()].filter(r=>r.length).map(summarize);maxNull(summaries,all,"mae");maxNull(summaries,all,"brier");
  summaries.sort((a,b)=>a.horizon-b.horizon||a.version.localeCompare(b.version)||a.signal.localeCompare(b.signal));
  const comparison=[];for(const H of HORIZONS)for(const signal of [...SIGNALS,"all4"]){const v2=summaries.find(s=>s.version==="roll_safe_v2"&&s.horizon===H&&s.signal===signal),v3=summaries.find(s=>s.version==="overlap_adjusted_v3"&&s.horizon===H&&s.signal===signal);if(v2&&v3)comparison.push({horizon:H,signal,v2_mae_skill:v2.mae_skill_log,v3_mae_skill:v3.mae_skill_log,delta_v3_minus_v2:v3.mae_skill_log-v2.mae_skill_log,v2_brier_skill:v2.brier_skill,v3_brier_skill:v3.brier_skill,delta_brier_v3_minus_v2:v3.brier_skill-v2.brier_skill});}
  const matched=[];
  for(const H of HORIZONS)for(const signal of [...SIGNALS,"all4"]){
    const a=all.filter(r=>r.version==="roll_safe_v2"&&r.horizon===H&&r.signal===signal),b=all.filter(r=>r.version==="overlap_adjusted_v3"&&r.horizon===H&&r.signal===signal),bm=new Map(b.map(r=>[r.origin_date,r])),pairs=a.filter(r=>bm.has(r.origin_date)).map(r=>[r,bm.get(r.origin_date)]);if(!pairs.length)continue;
    const metric=(r)=>({mae:Math.abs(r.actual)-Math.abs(r.actual-r.pred),br:brier(r.actual_class,[r.f_down,r.f_flat,r.f_up])-brier(r.actual_class,[r.p_down,r.p_flat,r.p_up])});
    const am=pairs.map(x=>metric(x[0])),cm=pairs.map(x=>metric(x[1]));matched.push({horizon:H,signal,common_origin_n:pairs.length,v2_mae_skill:mean(am.map(x=>x.mae)),v3_mae_skill:mean(cm.map(x=>x.mae)),delta_v3_minus_v2:mean(cm.map(x=>x.mae))-mean(am.map(x=>x.mae)),v2_brier_skill:mean(am.map(x=>x.br)),v3_brier_skill:mean(cm.map(x=>x.br)),delta_brier_v3_minus_v2:mean(cm.map(x=>x.br))-mean(am.map(x=>x.br))});
  }
  const liveRows=VERSIONS.map(v=>live(series[v],FEATURES));
  const liveForecasts=[];for(const version of VERSIONS)for(const H of HORIZONS)for(const names of [...SIGNALS.map(s=>[`turkey_${s}`]),FEATURES]){const r=liveForecast(mandi,series[version],version,H,names);if(r)liveForecasts.push(r);}
  fs.writeFileSync(path.join(OUTPUT,"summary.csv"),csv(summaries));fs.writeFileSync(path.join(OUTPUT,"predictions.csv"),csv(all));fs.writeFileSync(path.join(OUTPUT,"v2_v3_comparison.csv"),csv(comparison));fs.writeFileSync(path.join(OUTPUT,"matched_v2_v3_comparison.csv"),csv(matched));fs.writeFileSync(path.join(OUTPUT,"live_signals.csv"),csv(liveRows));fs.writeFileSync(path.join(OUTPUT,"live_forecasts.csv"),csv(liveForecasts));
  console.log(JSON.stringify({rows:all.length,summaries:summaries.length,bestMagnitude:[...summaries].sort((a,b)=>b.mae_skill_log-a.mae_skill_log).slice(0,5),bestDirection:[...summaries].sort((a,b)=>b.brier_skill-a.brier_skill).slice(0,5),live:liveRows,liveForecasts},null,2));
}
main();
