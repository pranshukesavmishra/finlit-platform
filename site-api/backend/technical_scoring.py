"""ST/LT v14.3 scoring signals. Source: owner's Pine lines 298–958.

Includes dependencies used by scores even where their settings were grouped under
trade-plan inputs. Excludes entry/exit plans, targets, sizing and backtests.
"""
import statistics

try:
    from .technical_series import ema, sma, rma, rsi, macd, atr_adx, obv, rolling, percentrank, linreg, weekly_closes, benchmark_pack, relative_strength
    from .technical_patterns import swing_patterns
except ImportError:
    from technical_series import ema, sma, rma, rsi, macd, atr_adx, obv, rolling, percentrank, linreg, weekly_closes, benchmark_pack, relative_strength
    from technical_patterns import swing_patterns


def scoring_signals(bars, benchmarks, shares_cr, as_of):
    """Return factor signals plus the stage/benchmark observations actually used."""
    st, lt, meta = {}, {}, {}
    if not bars:
        return st, lt, meta
    c, h, l, o, v = ([row[key] for row in bars] for key in ("close","high","low","open","volume"))
    n, last = len(bars), len(bars)-1
    e = {length:ema(c,length) for length in (9,20,50,100,200)}
    atr, adx = atr_adx(bars)
    avg50, vol3 = sma(v,50), sma(v,3)
    ext = [(price-average)/a if a is not None and a > 0 else None for price,average,a in zip(c,e[20],atr)]
    ranges = [high-low for high,low in zip(h,l)]
    patterns = swing_patterns(bars,avg50)
    highs60, lows15 = rolling(h,60,max,False), rolling(l,15,min,False)
    highs20, lows20 = rolling(h,20,max,False), rolling(l,20,min,False)
    mean150 = sma(c,150)
    slopes = [mean150[i]/mean150[i-50]-1 if i>=50 and mean150[i-50] is not None else None for i in range(n)]
    stages, fresh, breakouts = [], [], []
    last_breakout = last_not_two = None
    previous_non_two = 1
    for i in range(n):
        breakout = i>=60 and avg50[i] is not None and c[i]>highs60[i-1] and max(v[max(0,i-2):i+1])>1.5*avg50[i]
        if breakout:
            last_breakout = i
        breakouts.append(last_breakout)
        stage = None
        if slopes[i] is not None:
            stage = (2 if c[i]>mean150[i] else 3) if slopes[i]>.015 else 4 if slopes[i]<-.015 else 3 if i>=50 and slopes[i-50] is not None and slopes[i-50]>.015 else 2 if c[i]>mean150[i] and last_breakout is not None and i-last_breakout<=20 else 1
        if stage != 2:
            if stage is not None:
                previous_non_two = stage
            last_not_two = i
        stages.append(stage)
        fresh.append(stage==2 and previous_non_two==1 and last_not_two is not None and i-last_not_two<=60)
    stage = stages[-1]
    meta.update(stage=stage, freshStage2=fresh[-1], slope150Pct=slopes[-1]*100 if slopes[-1] is not None else None)
    sg = lambda condition: 1. if condition else -1.
    if n>=200 and adx[-1] is not None:
        mult = 1. if adx[-1]>25 else .5 if adx[-1]<20 else .75
        st["ema_stack"] = ((sg(e[9][-1]>e[20][-1])+sg(e[20][-1]>e[50][-1]))/2*mult, f"EMA 9 / 20 / 50: {e[9][-1]:.2f} / {e[20][-1]:.2f} / {e[50][-1]:.2f}; ADX {adx[-1]:.1f}.")
        st["price_ema20"] = ((sg(c[-1]>e[20][-1])+sg(e[20][-1]>e[20][-4]))/2*mult, f"Close {c[-1]:.2f}; EMA 20 {e[20][-1]:.2f}, {'rising' if e[20][-1]>e[20][-4] else 'flat or falling'} over three sessions; ADX {adx[-1]:.1f}.")
        line, signal, histogram = macd(c)
        st["macd"] = ((sg(line[-1]>signal[-1])+sg(histogram[-1]>histogram[-2]))/2*mult, f"MACD {line[-1]:.2f}; signal {signal[-1]:.2f}; histogram {'rising' if histogram[-1]>histogram[-2] else 'flat or falling'}.")
        r = rsi(c)[-1]
        if r is not None:
            bullish = c[-1]>e[200][-1] and e[50][-1]>e[200][-1]
            bearish = c[-1]<e[200][-1] and e[50][-1]<e[200][-1]
            bull = -.5 if r>80 else .5 if r>75 else 1. if r>=55 else .5 if r>=45 else 0. if r>=40 else -1.
            bear = 0. if r>=60 else -.5 if r>=40 else -1.
            neutral = 1. if 55<=r<=70 else .5 if 70<r<=80 else 0. if 45<=r<55 else -.5 if 30<=r<45 or r>80 else -1.
            st["rsi"] = (bull if bullish else bear if bearish else neutral, f"Daily RSI (14): {r:.1f}; {'bullish' if bullish else 'bearish' if bearish else 'neutral'} price regime.")
        else:
            st["rsi"] = (None, "Daily RSI is undefined because the observed history has neither gains nor losses.")
    if n>=50:
        ob = obv(bars)
        st["obv"] = (sg(ob[-1]>ema(ob,20)[-1]), "OBV is above its 20-day EMA." if ob[-1]>ema(ob,20)[-1] else "OBV is at or below its 20-day EMA.")
        if ext[-1] is not None:
            st["extension"] = (1. if ext[-1]<2 else -.5 if ext[-1]<3 else -1., f"Price extension: {ext[-1]:.2f} ATR above EMA 20.")
        else:
            st["extension"] = (None, "ATR is zero or unavailable, so price extension cannot be calculated.")
        up = c[-1]>e[50][-1] and e[9][-1]>e[20][-1]>e[50][-1]
        down = c[-1]<e[50][-1] and e[9][-1]<e[20][-1]<e[50][-1]
        tight_up = c[-1]>=e[9][-1] and (c[-1]-e[9][-1])/e[9][-1]<.02
        tight_down = c[-1]<=e[9][-1] and (e[9][-1]-c[-1])/e[9][-1]<.02
        scan = up and tight_up and l[-1]<=e[9][-1] and l[-2]<=e[9][-2]*1.01 and l[-3]<=e[9][-3]*1.01 and l[-4]<=e[9][-4] and v[-1]>100000
        touch_up = sum(l[i]<=e[9][i]*1.01 and c[i]>=e[9][i]*.99 for i in range(n-5,n))
        touch_down = sum(h[i]>=e[9][i]*.99 and c[i]<=e[9][i]*1.01 for i in range(n-5,n))
        dojis = sum(h[i]>l[i] and abs(c[i]-o[i])<=.35*ranges[i] and c[i]>=e[9][i]*.99 for i in range(n-5,n))
        bull = (1. if scan else .75 if touch_up>=4 else .5 if touch_up>=3 else 0.) if up and tight_up else 0.
        if bull>0 and dojis>=2:
            bull = min(1.,bull+.25)
        bear = (-1. if touch_down>=4 else -.5 if touch_down>=3 else 0.) if down and tight_down else 0.
        st["consolidation"] = (bull+bear, f"{touch_up}/5 upward EMA touches; {touch_down}/5 downward touches; {dojis} constructive small-body candles.")
        gap = (o[-1]/c[-2]-1)*100
        breakaway = gap>2 and ext[-2] is not None and ext[-2]<1.5 and c[-1]>o[-1]
        exhaustion = gap>2 and ext[-2] is not None and ext[-2]>3 and c[-1]<o[-1]
        st["gap"] = (1. if breakaway else -1. if exhaustion else -.5 if gap<-2 and c[-1]<c[-2] else 0., f"Opening gap: {gap:+.2f}%; " + ("breakaway gap." if breakaway else "exhaustion gap." if exhaustion else "no directional gap signal."))
        for target, key, label in ((st,"sfp_s","Swing failure"),(lt,"sfp_l","Major swing failure")):
            value = patterns[-1][key]
            detail = f"{label}: {'bullish' if value>0 else 'bearish'}, {'confirmed' if abs(value)==1 else 'awaiting confirmation'}." if value else f"No active {label.lower()}; neutral."
            target["sfp"] = (value,detail)
        migration = patterns[-1]["migration"]
        descriptions = {1.:"Value area entirely above the preceding swing.", .5:"Overlapping value area; point of control is higher.", -.5:"Overlapping value area; point of control is lower.", -1.:"Value area entirely below the preceding swing.", 0.:"Balanced value area."}
        st["value_migration"] = (migration, descriptions[migration] if patterns[-1]["has_prior_profile"] else "No preceding swing profile; neutral under the model's rule.")
        # Candle priority follows the source exactly, including the dry-pullback bonus.
        a, span, body = atr[-1], ranges[-1], abs(c[-1]-o[-1])
        if a is not None and a>0:
            clv = (c[-1]-l[-1])/span if span>0 else .5
            upper = (h[-1]-max(o[-1],c[-1]))/span if span>0 else 0.
            lower = (min(o[-1],c[-1])-l[-1])/span if span>0 else 0.
            hammer, engulf = lower>=.5 and clv>=.6, c[-1]>o[-1] and c[-2]<o[-2] and c[-1]>=o[-2] and o[-1]<=c[-2]
            doji_e9 = span>0 and body<=.35*span and c[-1]>=e[9][-1] and l[-1]<=e[9][-1]+.25*a and c[-1]>e[20][-1] and e[9][-1]>e[20][-1]
            profile = patterns[-1]["profile"]
            near_poc = profile is not None and (abs(c[-1]-profile["poc"])<=.5*a or l[-1]<=profile["poc"]<=h[-1])
            strong = c[-1]>o[-1] and clv>=.7 and body>=.5*span
            reject = upper>=.5 and h[-1]>=max(h[-21:-1])*.99
            wide = c[-1]<o[-1] and clv<=.3 and span>=1.2*a
            change = c[-1]-c[-2]
            big = n>=62 and change>0 and change>=max(c[i]-c[i-1] for i in range(n-61,n-1)) and span>=max(ranges[-61:-1])
            climax = stage==2 and c[-1]/lows15[-1]-1>=.25 and (big or exhaustion or (c[-1]-e[50][-1])/a>=7)
            if climax:
                raw, description = -1., "Climax run."
            elif (hammer or engulf) and l[-1]<=e[9][-1]+.25*a and c[-1]>e[20][-1]:
                raw, description = 1., "Hammer or bullish engulfing at EMA support."
            elif doji_e9 and near_poc:
                raw, description = 1., "Small-body candle at EMA 9 and the point of control."
            elif strong:
                raw, description = .75, "Strong bullish candle."
            elif reject or wide:
                raw, description = -1., "Upper-wick rejection or wide bearish candle."
            elif doji_e9:
                raw, description = .5, "Small-body candle near EMA 9."
            else:
                raw, description = 0., "No directional candle signal."
            bonus = .25 if vol3[-1]<.8*avg50[-1] and c[-1]>e[20][-1] and c[-1]<c[-4] else 0.
            st["candles"] = (max(-1.,min(1.,raw+bonus)), description + (" Dry volume on the pullback adds support." if bonus else ""))
    # BB/Keltner squeeze plus width percentile; population standard deviation.
    basis, std = sma(c,20), rolling(c,20,statistics.pstdev)
    tr = [h[0]-l[0]]+[max(h[i]-l[i],abs(h[i]-c[i-1]),abs(l[i]-c[i-1])) for i in range(1,n)]
    atr20 = rma(tr,20)
    width = [4*s/b if s is not None and b is not None else None for s,b in zip(std,basis)]
    ranks = percentrank(width,126)
    momentum = linreg([price-((high+low)/2+mean)/2 if mean is not None else None for price,high,low,mean in zip(c,highs20,lows20,basis)],20)
    squeeze = [s is not None and a is not None and 2*s<1.5*a for s,a in zip(std,atr20)]
    releases = [i for i in range(1,n) if squeeze[i-1] and not squeeze[i]]
    if ranks[-1] is not None and momentum[-1] is not None:
        fired = bool(releases) and last-releases[-1]<=3 and not squeeze[-1] and momentum[-1]>0 and momentum[-2] is not None and momentum[-1]>momentum[-2]
        value = 1. if fired else .5 if squeeze[-1] and momentum[-1]>0 else -.25 if squeeze[-1] else -.5 if ranks[-1]>80 else 0.
        st["squeeze"] = (value, "Squeeze breakout." if fired else "Squeeze forming." if squeeze[-1] else "Expanded volatility." if ranks[-1]>80 else "Normal volatility.")
    if n>=220:
        distance = c[-1]/e[200][-1]-1
        lt["price_ema200"] = ((1. if distance>0 else -1.) if abs(distance)>.02 else 0., f"Price is {distance*100:+.1f}% from EMA 200.")
        lt["ema200_slope"] = (sg(e[200][-1]>e[200][-21]), "EMA 200 is rising over 20 sessions." if e[200][-1]>e[200][-21] else "EMA 200 is flat or falling over 20 sessions.")
        for key, length in (("ema50_200",50),("ema100_200",100)):
            lt[key] = (sg(e[length][-1]>e[200][-1]), f"EMA {length}: {e[length][-1]:.2f}; EMA 200: {e[200][-1]:.2f}.")
        obv_up = ema(obv(bars),50)[-1]>ema(obv(bars),150)[-1]
        lt["obv_trend"] = (sg(obv_up), f"OBV's 50-day EMA is {'above' if obv_up else 'at or below'} its 150-day EMA.")
    if n>=252:
        hi, lo = max(c[-252:]), min(c[-252:])
        lt["structure"] = (1. if c[-1]>=.85*hi and c[-1]>=1.3*lo else -1. if c[-1]<.6*hi else 0., f"252-session closing high / low: {hi:.2f} / {lo:.2f}.")
    if stage is not None:
        value = 1. if stage==2 and fresh[-1] else .5 if stage==2 else 0. if stage==1 else -.75 if stage==3 else -1.
        lt["stage"] = (value, f"Stage {stage}: " + ("fresh advance." if stage==2 and fresh[-1] else "established advance." if stage==2 else "basing." if stage==1 else "topping." if stage==3 else "declining."))
        count = sum(v[i]>1.2*avg50[i] for i in range(n-3,n))
        recent = breakouts[-1] is not None and last-breakouts[-1]<=10
        lt["volume_persistence"] = (1. if recent and count>=2 else 0. if recent and count==1 else -.5 if recent else .5 if stage==2 and count>=2 else 0., f"{count} of the last three sessions exceeded 1.2 times their 50-day average volume.")
    weekly = weekly_closes(bars,as_of)
    if len(weekly)>=35:
        r = rsi(weekly)[-1]
        if r is not None:
            lt["weekly_rsi"] = (1. if 55<=r<=75 else 0. if 45<=r<55 else -1. if r<40 else -.5, f"Previous-week RSI (14): {r:.1f}.")
        else:
            lt["weekly_rsi"] = (None, "Weekly RSI is undefined because the observed history has neither gains nor losses.")
        line, signal, _ = macd(weekly)
        lt["weekly_macd"] = ((sg(line[-1]>signal[-1])+sg(line[-1]>0))/2, f"Previous-week MACD {line[-1]:.2f}; signal {signal[-1]:.2f}.")
    packs = {name:benchmark_pack(value["bars"],ema) for name,value in benchmarks.items() if value.get("bars")}
    picked, names, betas, rank_st, rank_lt = relative_strength(bars,packs,shares_cr)
    meta.update(benchmark=names[-1], benchmarksUsed=sorted(set(names[-505:])), beta=betas[-1], rsRatingST=rank_st[-1], rsRatingLT=rank_lt[-1])
    rs_signal = lambda rank: 1. if rank>=85 else .5 if rank>=70 else 0. if rank>=40 else -.5 if rank>=20 else -1.
    for target, rank in ((st,rank_st[-1]),(lt,rank_lt[-1])):
        if rank is not None:
            target["rs_rating"] = (rs_signal(rank), f"Beta-adjusted relative strength percentile: {rank:.1f}; benchmark: {names[-1]}.")
        else:
            target["rs_rating"] = (None, "Aligned stock and benchmark history is insufficient for the beta-adjusted relative strength percentile.")
    benchmark = picked[-1]
    rs_line = [row["close"]/b["close"] if b["close"] is not None else None for row,b in zip(bars,picked)]
    if n>=25 and all(benchmark[k] is not None for k in ("close","hi20","hi252","ll")):
        bdd = (benchmark["hi20"]-benchmark["close"])/benchmark["hi20"]*100
        sdd = (max(h[-20:])-c[-1])/max(h[-20:])*100
        weak = bdd>=4
        higher_low = min(l[-5:])>min(l[-25:-5])
        leader = weak and sdd<=.5*bdd and c[-1]>e[50][-1]
        strong = leader and (sdd<=3 or (benchmark["ll"] and higher_low))
        laggard = weak and sdd>=1.5*bdd
        st["leadership"] = (1. if strong else .5 if leader else -.5 if laggard else 0., f"Stock / benchmark drawdown over 20 sessions: {sdd:.1f}% / {bdd:.1f}%.")
        if n>=252 and all(x is not None for x in rs_line[-252:]):
            rs_hi, rs_lo = rs_line[-1]>=max(rs_line[-252:]), rs_line[-1]<=min(rs_line[-252:])
            first = h[-1]>=max(h[-252:]) and benchmark["close"]<.95*benchmark["hi252"]
            lt["leadership"] = (1. if first or (rs_hi and c[-1]<max(h[-252:])*.97) else .75 if rs_hi else .5 if leader else -1. if rs_lo else -.5 if laggard else 0., f"RS line at 52-week {'high' if rs_hi else 'low' if rs_lo else 'mid-range'}; benchmark: {names[-1]}.")
        else:
            lt["leadership"] = (None, "A complete aligned 252-session stock/index window is unavailable.")
    else:
        for target in (st,lt):
            target["leadership"] = (None, "A complete aligned 252-session stock/index window is unavailable.")
    return st, lt, meta
