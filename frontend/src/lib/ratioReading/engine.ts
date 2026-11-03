// @ts-nocheck: the rules engine as handed over (plain JavaScript, no dependencies); its behaviour is pinned by engine.test.ts
/*
 * FinLit · Ratio history reading ("What it tells you")
 * --------------------------------------------------------------
 * Pure, rule-based. No company-specific text: every line is built from the
 * numbers in /api/stocks/{SYMBOL}/ratios (history.periods + history.rows)
 * plus each ratio's label / unit / "better" direction from `latest`.
 *
 *   import {readAll, kindOf} from './ratioReading';
 *   const out = readAll(periods, rows, metaByKey, {kind});
 *   // kind: 'company' (default) or 'lender'  (kindOf(profile))
 *   // out[key] = {vd, label, tone, group, l1, l2, nm, link}
 *   //   vd     verdict id (improving, recovering, above, steady, watch, below,
 *   //          shifted, weak, context, nodata)
 *   //   label  chip text, tone: g | a | r | n | b
 *   //   group  better | steady | watch | weak | context   (for filters / counts)
 *   //   l1     what happened to the number   (plain text)
 *   //   l2     what it means in plain words  (plain text)
 *   //   nm     per-year reason when a value is not meaningful (or null)
 *   //   link   optional section id to point to ('dupont', 'earnings-cash')
 */
  const P10 = d => Math.pow(10, d);
  const rnd = (v, d) => (Math.round(Math.abs(v) * P10(d) + 1e-7) / P10(d)).toFixed(d);
  const ng = v => (v < 0 ? '−' : '');
  const grp = s => { if (s.length <= 3) return s; const l = s.slice(-3); return s.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ',') + ',' + l; };
  const int = v => ng(v) + grp(String(Math.round(Math.abs(v))));
  const r1 = v => ng(v) + rnd(v, 1), r2 = v => ng(v) + rnd(v, 2), pc = v => Math.round(v * 100) + '%';

  const PROFIT = new Set(['ebit_margin', 'ebitda_margin', 'net_margin', 'operating_margin', 'pretax_margin', 'roa', 'roce', 'roe', 'rota', 'interest_coverage']);
  const DEBT_TINY = {debt_to_equity: 0.15, lt_debt_to_equity: 0.15, debt_to_assets: 0.08, debt_to_fcf: 1};
  const FLOOR = {'%': 1, x: 0.05, days: 5};

  function kindOf(profile) {
    if (!profile) return 'company';
    const f = [profile.industry, profile.sector, profile.subIndustry].filter(Boolean);
    if (f.some(s => /fintech/i.test(s))) return 'company';
    return f.some(s => /^(banks?|finance|insurance)$/i.test(s.trim()) || /bank|nbfc|non banking|housing finance|insurance/i.test(s)) ? 'lender' : 'company';
  }

  // ---- what each ratio means (level phrase, rule of thumb, so-what by direction) ----
  const marg = (what, lossWhat) => ({lvl: L => `About ₹${r1(L)} of ${what} per ₹100 of sales`, neg: L => `${lossWhat} of about ₹${r1(-L)} per ₹100 of sales`, good: 'Costs are taking a smaller slice of sales', bad: 'Costs are taking a bigger slice of sales'});
  const RX = {
    asset_turnover: {lvl: L => `Each ₹1 of assets brings in about ₹${r2(L)} of sales`, good: 'Assets are producing more sales', bad: 'The asset base is growing faster than sales', link: 'dupont'},
    cash_conversion_cycle: {lvl: L => L < 0 ? `Suppliers fund day-to-day running for about ${int(-L)} days` : `Cash is now tied up for about ${int(L)} days in day-to-day running`, good: 'Less cash is tied up in day-to-day running', bad: 'More cash is tied up in day-to-day running', ccc: true},
    current_ratio: {lvl: L => L < 1 ? `Current assets cover about ${pc(L)} of bills due within a year` : `Current assets cover bills due within a year ${r2(L)} times`, thumb: L => L >= 1.5 ? ['ok', 'a comfortable cushion'] : L >= 1 ? ['ok', 'a thin cushion'] : ['weak', 'tight'], good: 'More short-term cushion', bad: 'Less short-term cushion'},
    debt_to_assets: {lvl: L => `Borrowing funds about ${pc(L)} of assets`, thumb: L => L >= 1 ? ['weak', 'debts are larger than assets'] : L < 0.3 ? ['ok', 'low'] : L < 0.5 ? ['ok', 'moderate'] : ['weak', 'high'], good: 'Less of the business is funded by borrowing', bad: 'More of the business is funded by borrowing'},
    debt_to_equity: {lvl: L => `₹${r2(L)} of debt for every ₹1 of owners' money`, thumb: L => L < 0.5 ? ['ok', 'still conservative (under 0.5)'] : L < 1 ? ['ok', 'moderate'] : ['weak', 'high'], good: 'Equity is growing faster than borrowing', bad: 'Borrowing is growing faster than equity'},
    debt_to_fcf: {lvl: L => `Debt equals about ${r1(L)} years of free cash flow`, thumb: L => L < 3 ? ['ok', 'quick to repay'] : L < 6 ? ['ok', 'manageable'] : ['weak', 'slow to repay'], good: 'Free cash flow has grown faster than debt', bad: 'Debt is outgrowing free cash flow'},
    debtor_days: {lvl: L => `Customers take about ${int(L)} ${Math.round(L) === 1 ? 'day' : 'days'} to pay`, good: 'Faster collections free up cash', bad: 'Slower collections tie up cash', link: 'earnings-cash', linkWhen: 'bad', cc: ['debtor', 'customers are paying slower', 'customers are paying faster']},
    dividend_payout: {lvl: L => L <= 0 ? 'Paid no dividend in the latest year' : `Pays out about ₹${rnd(L, 0)} of every ₹100 of profit and keeps the rest`, up: 'Paying out a bigger share of profit', down: 'Keeping more profit to reinvest'},
    ebit_margin: marg('operating profit after depreciation', 'Operating loss'),
    ebitda_margin: marg('operating profit before depreciation', 'Operating loss'),
    effective_tax_rate: {lvl: L => `Pays about ${rnd(L, 0)}% of pre-tax profit as tax`, thumb: L => Math.abs(L - 25) <= 4 ? ['ok', 'close to the usual 25%'] : L < 15 ? ['weak', 'well below the usual 25%: check why'] : ['ok', L < 25 ? 'below the usual 25%' : 'above the usual 25%'], up: 'A higher tax rate trims profit', down: 'A lower tax rate lifts profit; check it can last'},
    financial_leverage: {lvl: L => `₹${r2(L)} of assets for every ₹1 of equity`, thumb: L => L < 3 ? ['ok', 'moderate'] : ['weak', 'high'], good: 'Less reliance on outside money', bad: 'Assets are growing faster than equity: this lifts ROE but adds risk', link: 'dupont'},
    gross_margin: {lvl: L => `Keeps about ₹${r1(L)} of every ₹100 of sales after direct costs`, good: 'Direct costs are taking a smaller slice', bad: 'Direct costs are taking a bigger slice'},
    interest_coverage: {lvl: L => L >= 20 ? `Interest is a small cost: operating profit covers it ${int(L)} times` : `Operating profit covers interest ${r1(L)} times`, neg: () => 'Operating profit does not cover interest', thumb: L => L >= 20 ? null : L >= 3 ? ['ok', 'comfortable (above 3×)'] : L >= 1.5 ? ['ok', 'adequate'] : ['weak', 'weak (under 1.5×)'], good: 'Profit is growing faster than interest costs', bad: 'Interest costs are growing faster than profit'},
    inventory_days: {lvl: L => `Holds about ${int(L)} days of stock`, good: 'Less cash is tied up in stock', bad: 'More cash is tied up in stock', cc: ['inventory', 'stock is held longer', 'stock is held for less time']},
    lt_debt_to_equity: {lvl: L => `₹${r2(L)} of long-term debt for every ₹1 of equity`, thumb: L => L < 0.5 ? ['ok', 'still low (under 0.5)'] : L < 1 ? ['ok', 'moderate'] : ['weak', 'high'], good: 'Less long-term borrowing', bad: 'More long-term borrowing, usually to fund new projects'},
    net_margin: {lvl: L => `Keeps about ₹${r1(L)} of every ₹100 of sales as profit`, neg: L => `Loses about ₹${r1(-L)} on every ₹100 of sales`, good: 'More of each sale is left as profit', bad: 'Less of each sale is left as profit', link: 'dupont'},
    operating_margin: marg('operating profit', 'Operating loss'),
    payable_days: {lvl: L => `Pays suppliers in about ${int(L)} days`, up: 'Taking longer to pay suppliers frees cash but can strain them', down: 'Paying suppliers faster uses cash', cc: ['payable', 'suppliers are being paid faster', 'suppliers are being paid more slowly']},
    pretax_margin: {lvl: L => `About ₹${r1(L)} of every ₹100 of sales is left after interest and depreciation`, neg: L => `Pre-tax loss of about ₹${r1(-L)} per ₹100 of sales`, good: 'More is left before tax', bad: 'Less is left before tax'},
    quick_ratio: {lvl: L => L < 1 ? `Without selling stock, liquid assets cover about ${pc(L)} of bills due within a year` : `Liquid assets alone cover bills due within a year ${r2(L)} times`, thumb: L => L >= 1 ? ['ok', 'comfortable'] : L >= 0.6 ? ['ok', 'common for businesses that hold a lot of stock'] : ['weak', 'thin'], good: 'More liquid cushion', bad: 'Less liquid cushion'},
    retention_ratio: {lvl: L => L < 0 ? 'Paid out more than its profit in the latest year' : `Keeps about ₹${rnd(L, 0)} of every ₹100 of profit to reinvest`, up: 'Reinvesting a bigger share of profit', down: 'Paying out more of its profit'},
    roa: {lvl: L => `Earns about ₹${r1(L)} a year for every ₹100 of assets`, neg: L => `Loses about ₹${r1(-L)} a year for every ₹100 of assets`, thumb: L => L < 5 ? ['info', 'low'] : L < 10 ? ['info', 'moderate'] : ['info', 'strong'], good: 'Assets are earning more', bad: 'Profit is not keeping up with the asset base'},
    roce: {lvl: L => `Earns about ₹${r1(L)} for every ₹100 of capital employed`, neg: L => `Loses about ₹${r1(-L)} for every ₹100 of capital employed`, thumb: L => L < 12 ? ['info', 'below the 12% many investors look for'] : L < 18 ? ['info', 'healthy'] : ['info', 'strong'], good: 'Capital is earning more', bad: 'Capital is earning less'},
    roe: {lvl: L => `Earns about ₹${r1(L)} for every ₹100 of shareholders' money`, neg: L => `Loses about ₹${r1(-L)} for every ₹100 of shareholders' money`, thumb: L => L < 12 ? ['info', 'low (under 12%)'] : L < 18 ? ['info', 'healthy'] : ['info', 'strong'], good: 'Returns to shareholders are improving', bad: 'Returns to shareholders are slipping', link: 'dupont'},
    rota: {lvl: L => `Earns about ₹${r1(L)} for every ₹100 of tangible assets`, neg: L => `Loses about ₹${r1(-L)} for every ₹100 of tangible assets`, thumb: L => L < 5 ? ['info', 'low'] : L < 10 ? ['info', 'moderate'] : ['info', 'strong'], good: 'Tangible assets are earning more', bad: 'Profit is not keeping up with tangible assets'}
  };
  // banks, NBFCs and insurers read some ratios differently
  const RXL = {
    roa: {thumb: L => L < 1 ? ['info', 'low for a lender (under 1%)'] : L < 2 ? ['info', 'healthy for a lender'] : ['info', 'strong for a lender']},
    rota: {thumb: L => L < 1 ? ['info', 'low for a lender (under 1%)'] : L < 2 ? ['info', 'healthy for a lender'] : ['info', 'strong for a lender']},
    financial_leverage: {thumb: () => ['ok', 'normal for a lender, which lends out borrowed money'], bad: 'More of the balance sheet is funded by borrowing', link: null},
    net_margin: {lvl: L => `Keeps about ₹${r1(L)} of every ₹100 of income as profit`, good: 'More of each rupee of income is left as profit', bad: 'Less of each rupee of income is left as profit', link: null},
    roce: {thumb: () => null},
    operating_margin: {lvl: L => `About ₹${r1(L)} of operating profit per ₹100 of income`},
    pretax_margin: {lvl: L => `About ₹${r1(L)} of every ₹100 of income is left before tax`}
  };

  const VD = {improving: ['Improving', 'g'], recovering: ['Recovering', 'g'], above: ['Above usual', 'g'], steady: ['Steady', 'n'], watch: ['Watch', 'a'], below: ['Below usual', 'a'], shifted: ['Shifted', 'a'], weak: ['Weakening', 'r'], context: ['Context', 'b'], nodata: ['Too little data', 'n']};
  const VGROUP = {improving: 'better', recovering: 'better', above: 'better', steady: 'steady', watch: 'watch', below: 'watch', shifted: 'watch', weak: 'weak', context: 'context', nodata: 'context'};

  // values that cannot be read as they stand
  function invalid(key, x, i, all) {
    const at = k => (all[k] ? all[k][i] : null);
    if (key === 'debt_to_fcf' && x < 0) return 'free cash flow was negative';
    if ((key === 'debt_to_equity' || key === 'lt_debt_to_equity' || key === 'financial_leverage') && x < 0) return 'equity was negative';
    if (key === 'roe') { const fl = at('financial_leverage'), de = at('debt_to_equity'); if ((fl != null && fl < 0) || (de != null && de < 0)) return 'equity was negative'; if (x > 150) return 'the equity base was too small to compare'; }
    if (key === 'effective_tax_rate') { const pt = at('pretax_margin'); if (pt != null && pt <= 0.05) return 'there was little or no pre-tax profit'; if (x < -5 || x > 60) return 'the value is unusual'; }
    if (key === 'rota') { const ra = at('roa'); if (ra != null && ((ra < 0) !== (x < 0) || (ra > 0 && x > 1.5 * ra + 5))) return 'it does not match ROA; check the data'; }
    if (/_days$|cash_conversion_cycle/.test(key) && Math.abs(x) > 500) return 'the value looks wrong; check the data';
    if ((key === 'ebitda_margin' || key === 'ebit_margin' || key === 'operating_margin') && x > 100) return 'it exceeds sales, likely one-off items';
    return null;
  }

  function readOne(key, periods, raw, meta, ctx, all) {
    const lender = ctx.kind === 'lender';
    const R = Object.assign({}, RX[key] || {lvl: L => `${meta.l || key}: ${L}`}, lender ? RXL[key] || {} : {});
    const n = raw.length, yr = i => periods[i];
    const nm = raw.map((x, i) => (x == null ? null : invalid(key, x, i, all)));
    const v = raw.map((x, i) => (x == null || nm[i] ? null : x));
    const idx = v.map((x, i) => (x == null ? -1 : i)).filter(i => i >= 0), N = idx.length;
    const unit = meta.u, g = meta.b === 'higher' ? 1 : meta.b === 'lower' ? -1 : 0;
    const num = x => unit === '%' ? r1(x) : unit === 'days' ? int(x) : unit === 'x' ? (Math.abs(x) >= 20 ? int(x) : Math.abs(x) >= 10 ? r1(x) : r2(x)) : String(x);
    const suf = (x) => unit === '%' ? '%' : unit === 'days' ? (Math.round(Math.abs(x)) === 1 ? ' day' : ' days') : unit === 'x' ? '×' : '';
    const num2 = x => unit === '%' ? r2(x) : num(x);
    const pair = (a, b) => (unit === '%' && num(a) === num(b) && a !== b ? [num2(a), num2(b)] : [num(a), num(b)]);
    const F = x => num(x) + suf(x), FR = (a, b) => { const [p, q] = pair(a, b); return p === q ? F(a) : `${p}–${q}${suf(b)}`; }, FA = (a, b) => { const [p, q] = pair(a, b); return `${p} → ${q}${suf(b)}`; };
    const reasons = {}; nm.forEach((r, i) => { if (r) (reasons[r] = reasons[r] || []).push(yr(i)); });
    const nmNote = Object.entries(reasons).map(([r, ys]) => `${ys.join(', ')} not meaningful: ${r}.`).join(' ');
    const linkOk = (vd) => R.link && (!R.linkWhen || (R.linkWhen === 'bad' && (vd === 'weak' || vd === 'watch')));
    const out = (vd, l1, l2) => ({vd, label: VD[vd][0], tone: VD[vd][1], group: VGROUP[vd], l1, l2: [l2, nmNote].filter(Boolean).join(' ').trim(), nm, link: linkOk(vd) ? R.link : null});

    const thOk = L => R.thumb && (L >= 0 || key === 'effective_tax_rate');
    const level = L => { const th = thOk(L) ? R.thumb(Math.max(L, 0)) : null; return (L < 0 && R.neg ? R.neg(L) : R.lvl(L)) + (th ? `: ${th[1]}` : '') + '.'; };
    const vals = idx.map(i => v[i]);
    if (key === 'gross_margin' && vals.length && vals.slice(-5).every(x => x >= 99)) return out('context', 'Not meaningful for this business.', 'It reports no cost of goods, so gross margin is about 100% every year.');
    if (N < 3) return out('nodata', 'Not enough years with usable numbers to read a trend.', N ? `${yr(idx[N - 1])}: ${level(v[idx[N - 1]])}` : '');

    const Li = idx[N - 1], L = v[Li], Pi = idx[N - 2], P = v[Pi], latestTag = Li === n - 1 ? '' : ` (latest usable year ${yr(Li)})`;
    const mx = Math.max(...vals), mn = Math.min(...vals);
    const yrs = N === n ? `${N} years` : `the ${N} years with usable numbers`;
    if (mx - mn < 1e-9) {
      if (L === 0 && DEBT_TINY[key] != null) return out('steady', `Debt-free in all ${yrs}.`, 'No borrowing on the balance sheet.');
      if (key === 'dividend_payout' && L === 0) return out('context', `No dividend in any of the ${yrs}.`, 'All profit is kept in the business.');
      if (key === 'retention_ratio' && L === 100) return out('context', `Keeps all of its profit in every one of the ${yrs}.`, 'No dividend paid.');
      return out(g ? 'steady' : 'context', `Unchanged at ${F(L)} for ${yrs}.`, level(L));
    }
    const sorted = vals.slice().sort((a, b) => a - b), M = N % 2 ? sorted[(N - 1) / 2] : (sorted[N / 2 - 1] + sorted[N / 2]) / 2;
    const aM = Math.max(Math.abs(M), (mx - mn) / 4, FLOOR[unit] || 0.01);
    const W = idx.slice(-Math.min(5, N)), w5 = W.map((i, k) => [k, v[i]]);
    const wl = N >= 6 ? 'over the last five years' : `since ${yr(W[0])}`;
    const mx5 = Math.max(...w5.map(p => p[1])), mn5 = Math.min(...w5.map(p => p[1]));
    const pairs = []; for (let a = 0; a < w5.length; a++) for (let b = a + 1; b < w5.length; b++) pairs.push((w5[b][1] - w5[a][1]) / (w5[b][0] - w5[a][0]));
    pairs.sort((a, b) => a - b); const slope = pairs.length % 2 ? pairs[(pairs.length - 1) / 2] : (pairs[pairs.length / 2 - 1] + pairs[pairs.length / 2]) / 2; // Theil–Sen: one odd year cannot swing it
    let streak = 0, sdir = 0;
    for (let k = N - 1; k > 0; k--) { const a = v[idx[k]], b = v[idx[k - 1]]; if (idx[k] - idx[k - 1] !== 1) break; const d = Math.sign(a - b); if (!d) break; if (!sdir) sdir = d; if (d !== sdir) break; streak++; }
    const sStart = v[idx[N - 1 - streak]];
    const isMax = L === mx, isMin = L === mn, tie = vals.filter(x => x === L).length > 1;
    const moved = Math.abs(L - P) > 0.03 * aM;
    const range5 = (mx5 - mn5) / aM, s = g * slope / aM, d = g * (L - M) / aM;
    const F0i = idx[0], F0 = v[F0i];
    const sameSign = F0 > 0 && L > 0, start = sameSign ? g * (L - F0) / Math.abs(F0) : 0;
    const th = thOk(L) ? R.thumb(Math.max(L, 0)) : null, soft = th && th[0] === 'ok';
    const vsStart = sameSign && Math.abs(L - F0) / Math.abs(F0) > 0.12 && Math.abs(L - F0) > (FLOOR[unit] || 0) ? `${L > F0 ? 'up' : 'down'} from ${F(F0)} in ${yr(F0i)}` : '';
    let spike = null; const rng = mx - mn;
    for (let k = 1; k < N - 5; k++) { const a = v[idx[k - 1]], b = v[idx[k]], c = v[idx[k + 1]]; if ((b > a && b > c) || (b < a && b < c)) { if (Math.abs(b - (a + c) / 2) > 0.5 * rng) spike = {i: idx[k], b, hi: b > a}; } }
    const spikeTxt = spike ? ` (${yr(spike.i)}'s ${F(spike.b)} was a one-off ${spike.hi ? 'high' : 'low'})` : '';
    const tail = !g && spike ? spikeTxt : vsStart ? `, ${vsStart}` : spikeTxt;
    const updown = x => (x > 0 ? 'Rising' : 'Falling');
    const earlier = vals.slice(0, -1), oneOff = PROFIT.has(key) && key !== 'interest_coverage' && L > 0 && L > 2 * Math.max(0, ...earlier) + 20;
    const oneOffTxt = oneOff ? ` Unusually high against its own history: likely lifted by one-off items, so check before reading it as a trend.` : '';
    let l2 = level(L);

    // ---------- profit-type ratios that cross zero ----------
    if (g > 0 && PROFIT.has(key) && (L < 0 || P < 0)) {
      const posSince = (() => { let k = N - 1; while (k >= 0 && v[idx[k]] > 0) k--; return k < N - 1 ? yr(idx[k + 1]) : null; })();
      if (P < 0 && L > 0) return out('improving', `Turned positive in ${yr(Li)}: ${FA(P, L)}.`, l2 + (key === 'interest_coverage' ? ' Operating profit covers interest again.' : ' Back in profit after losses.') + oneOffTxt);
      if (P > 0 && L < 0) return out('weak', `Turned negative in ${yr(Li)}: ${FA(P, L)}.`, l2 + ' Back to a loss.');
      if (L > P) return out('recovering', `Losses narrowing${streak >= 2 && sdir > 0 ? ` ${streak} years running` : ''}: ${FA(streak >= 2 && sdir > 0 ? sStart : P, L)}${latestTag}.`, l2);
      return out('weak', `Losses widening: ${FA(P, L)}${latestTag}.`, l2);
    }
    const posSince = PROFIT.has(key) && mn < 0 ? (() => { let k = N - 1; while (k >= 0 && v[idx[k]] > 0) k--; return yr(idx[k + 1]); })() : null;

    // ---------- neutral ratios: describe, flag big shifts ----------
    if (!g) {
      const hi100 = key === 'dividend_payout' ? idx.filter(i => v[i] > 100).map(yr) : key === 'retention_ratio' ? idx.filter(i => v[i] < 0).map(yr) : [];
      const extra = hi100.length ? ` Paid out more than its profit in ${hi100.join(', ')}.` : '';
      if ((isMax || isMin) && moved && N >= 4) return out('shifted', `${isMax ? 'Highest' : 'Lowest'} in ${yrs}: ${FA(P, L)}${latestTag}.`, l2 + ` ${L > P ? R.up : R.down}.${ccDriver() ? ` This is ${ccDriver()}.` : ''}` + extra);
      const wide = (mx5 - mn5) / aM >= 0.25;
      return out('context', `${wide ? 'Ranged' : 'Stable at'} ${FR(mn5, mx5)} ${wl}${tail}.`, l2 + (ccDriver() ? ` This is ${ccDriver()}.` : '') + extra);
    }

    // ---------- directional verdict ----------
    let vd;
    const tiny = DEBT_TINY[key];
    if (tiny != null && mx <= tiny) {
      return out('steady', L > P && moved ? `Took on a little debt in ${yr(Li)}: ${FA(P, L)}, still almost debt-free.` : `Almost debt-free throughout: ${FR(mn, mx)}.`, l2);
    }
    if (key === 'interest_coverage' && mn5 >= 20) return out('steady', `Very high every year ${wl}: ${FR(mn5, mx5)}.`, l2);
    const jump = Math.abs(L - P) > 0.6 * aM, step = Math.abs(L - P) > 0.1 * aM; let why = '';
    if (range5 < 0.08) vd = 'steady';
    else if ((g > 0 ? isMin : isMax) && moved) vd = soft || Math.abs(L - P) < 0.05 * aM ? 'watch' : 'weak';
    else if (jump && g * (L - P) < 0) { vd = soft ? 'watch' : 'weak'; why = 'sharp'; }
    else if (streak >= 3 && sdir * g < 0) vd = d < -0.05 && !soft ? 'weak' : 'watch';
    else if ((g > 0 ? isMax : isMin) && moved) vd = 'improving';
    else if (jump && g * (L - P) > 0) { vd = 'improving'; why = 'sharp'; }
    else if (streak >= 3 && sdir * g > 0) vd = 'improving';
    else if (streak === 2 && sdir * g < 0 && step) { vd = 'watch'; why = 'streak2'; }
    else if (streak === 2 && sdir * g > 0 && step) { vd = 'improving'; why = 'streak2'; }
    else if (Math.abs(s) < 0.02 && Math.abs(d) < 0.05) vd = 'steady';
    else if (s < -0.02) vd = 'watch';
    else if (s > 0.02 && start < -0.10) vd = 'recovering';
    else if (d > 0.05) vd = 'above';
    else if (s > 0.02) vd = 'improving';
    else if (d < -0.05) vd = 'below';
    else vd = 'steady';

    const atWorst = (g > 0 ? isMin : isMax) && moved, atBest = (g > 0 ? isMax : isMin) && moved;
    const wWord = tie ? 'joint worst' : 'worst', bWord = tie ? 'Joint most favourable' : 'Most favourable';
    const since = posSince && posSince !== yr(F0i) ? ` (positive since ${posSince})` : '';
    let l1;
    if (atWorst && (vd === 'weak' || vd === 'watch')) l1 = streak >= 3 ? `${updown(sdir)} ${streak} years running (${FA(sStart, L)}), ${wWord} in ${yrs}.` : `${wWord[0].toUpperCase() + wWord.slice(1)} in ${yrs}: ${FA(P, L)} in ${yr(Li)}.`;
    else if (why === 'sharp') l1 = `${g * (L - P) < 0 ? (L < P ? 'Fell' : 'Rose') + ' sharply' : (L > P ? 'Jumped' : 'Dropped')} in ${yr(Li)}: ${FA(P, L)}.`;
    else if (streak >= 2 && (streak >= 3 || why === 'streak2') && ((sdir * g < 0 && (vd === 'weak' || vd === 'watch')) || (sdir * g > 0 && vd === 'improving'))) l1 = `${updown(sdir)} ${streak} years running: ${FA(sStart, L)}${since}${latestTag}.`;
    else if (vd === 'improving' && atBest) l1 = `${bWord} in ${yrs}: ${FA(P, L)}${latestTag}.`;
    else if (vd === 'watch') l1 = `Drifting ${slope > 0 ? 'higher' : 'lower'} ${wl}: ${FA(w5[0][1], L)}${L === P && N > 2 && P === v[idx[N - 3]] ? ', flat for the last two' : streak >= 2 && sdir * g > 0 ? `, though ${sdir > 0 ? 'up' : 'down'} the last two years` : ''}${latestTag}.`;
    else if (vd === 'improving') l1 = `Improving ${wl}: ${FA(w5[0][1], L)}${since}${latestTag}.`;
    else if (vd === 'recovering') { const wi = idx.reduce((b, i) => (b < 0 || g * v[i] < g * v[b] ? i : b), -1); l1 = `Recovering from ${F(v[wi])} in ${yr(wi)} to ${F(L)}${latestTag}, still ${g > 0 ? 'below' : 'above'} ${yr(F0i)}'s ${F(F0)}.`; }
    else if (vd === 'above') l1 = `Better than its usual level: ${F(L)}${latestTag} against ${/^(8|11|18)$/.test(String(N)) ? 'an' : 'a'} ${N}-year median of ${F(M)}${vsStart && Math.abs(F0 - M) > 0.05 * aM ? `, ${vsStart}` : ''}.`;
    else if (vd === 'below') l1 = `Worse than its usual level: ${F(L)}${latestTag} against ${/^(8|11|18)$/.test(String(N)) ? 'an' : 'a'} ${N}-year median of ${F(M)}.`;
    else l1 = `Steady ${wl}: ${FR(mn5, mx5)}${tail}${latestTag}.`;

    const lastBad = g * (L - P) < 0;
    if (R.ccc) l2 += cccWhy();
    else {
      let so = '';
      if (vd === 'weak' || vd === 'improving' || (vd === 'watch' && lastBad)) so = vd === 'improving' ? R.good : R.bad;
      const cd = ccDriver();
      if (so) l2 += ` ${so}.`; if (cd) l2 += ` This is ${cd}.`;
    }
    return out(vd, l1, l2 + oneOffTxt);

    // --- cash-cycle helpers (components: inventory + debtor − payable days) ---
    function comp(k) { const a = all[k]; if (!a) return null; const x = a[Li], y = a[Pi]; if (x == null || y == null || Math.abs(x) > 500 || Math.abs(y) > 500) return null; return {k, a: y, b: x, ch: (x - y) * (k === 'payable_days' ? -1 : 1)}; }
    function cccWhy() {
      const parts = ['inventory_days', 'debtor_days', 'payable_days'].map(comp).filter(Boolean);
      if (!parts.length || L === P) return '';
      const big = parts.sort((x, y) => Math.abs(y.ch) - Math.abs(x.ch))[0], c = RX[big.k].cc, worse = big.ch > 0, turned = P < 0 && L > 0;
      return ` ${turned ? 'Turned positive' : L > P ? 'Up' : 'Down'} mainly because ${worse ? c[1] : c[2]} (${c[0]} days ${int(big.a)} → ${int(big.b)})${turned ? ': the business now funds its own working capital instead of its suppliers' : ''}.`;
    }
    function ccDriver() {
      if (!R.cc || !all.cash_conversion_cycle) return '';
      const cc = all.cash_conversion_cycle, a = cc[Li], b = cc[Pi];
      if (a == null || b == null || Math.abs(a) > 500 || Math.abs(b) > 500 || Math.abs(a - b) < 10) return '';
      const parts = ['inventory_days', 'debtor_days', 'payable_days'].map(comp).filter(Boolean).sort((x, y) => Math.abs(y.ch) - Math.abs(x.ch));
      return parts.length && parts[0].k === key ? `the main reason the cash cycle ${a > b ? 'rose' : 'fell'}` : '';
    }
  }

  function readAll(periods, rows, metaByKey, ctx) {
    ctx = ctx || {}; const out = {};
    Object.keys(rows || {}).forEach(k => { try { out[k] = readOne(k, periods, rows[k], metaByKey[k] || {l: k, u: '', b: null}, ctx, rows); } catch (e) { out[k] = {vd: 'nodata', label: VD.nodata[0], tone: 'n', group: 'context', l1: 'Could not read this ratio.', l2: '', nm: rows[k].map(() => null), link: null}; } });
    return out;
  }

export { readAll, kindOf, VD, VGROUP };
