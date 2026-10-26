"""Scoring-only pivot, swing-failure and volume-profile rules from v14.3.

Confirmed pivots are inserted after sweeps on the confirmation bar. No trade
plans, orders, position sizing or simulated transactions belong in this module.
"""


def pivot(values, index, length, high=False):
    center = index - length
    if center < length:
        return None
    left, right = values[center-length:center], values[center+1:index+1]
    value = values[center]
    # Equal extrema on the left are allowed; a newer equal extreme wins.
    valid = value >= max(left) and value > max(right) if high else value <= min(left) and value < min(right)
    return value if valid else None


def volume_profile(bars, bins_count=24):
    if len(bars) < 2:
        return None
    bottom, top = min(row["low"] for row in bars), max(row["high"] for row in bars)
    size = (top - bottom) / bins_count
    if size <= 0:
        return None
    bins = [0.] * bins_count
    for row in bars:
        low, high, volume = row["low"], row["high"], row["volume"]
        first = max(0, min(bins_count - 1, int((low - bottom) / size)))
        last = max(0, min(bins_count - 1, int((high - bottom) / size)))
        if high <= low or first == last:
            bins[first] += volume
        else:
            for b in range(first, last + 1):
                overlap = min(high, bottom + (b + 1) * size) - max(low, bottom + b * size)
                if overlap > 0:
                    bins[b] += volume * overlap / (high - low)
    poc = bins.index(max(bins))
    lo = hi = poc
    included = bins[poc]
    target = .7 * sum(bins)
    while included < target and (lo > 0 or hi < bins_count - 1):
        below = bins[lo - 1] if lo > 0 else -1
        above = bins[hi + 1] if hi < bins_count - 1 else -1
        if above >= below:
            hi += 1
            included += above
        else:
            lo -= 1
            included += below
    return {"poc": bottom + (poc + .5) * size, "vah": bottom + (hi + 1) * size, "val": bottom + lo * size}


def swing_patterns(bars, average_volume):
    highs, lows = [b["high"] for b in bars], [b["low"] for b in bars]
    levels = {key: [] for key in ("bull_s", "bear_s", "bull_l", "bear_l")}
    states, result = {}, []
    last_low, prior_profile, previous_profile = None, None, None
    for index, bar in enumerate(bars):
        pivots = {key: pivot(highs if key.startswith("bear") else lows, index, length, key.startswith("bear"))
                  for key, length in (("bull_s",5),("bear_s",5),("bull_l",15),("bear_l",15))}
        for key, entries in levels.items():
            bearish = key.startswith("bear")
            swept = []
            for value in entries[:]:
                hit = bar["high"] > value if bearish else bar["low"] < value
                if hit:
                    failed = bar["close"] < value if bearish else bar["close"] > value
                    if failed:
                        swept.append(value)
                    entries.remove(value)
            if pivots[key] is not None:
                entries.append(pivots[key])
                del entries[:-10]
            new = bool(swept) and average_volume[index] is not None and bar["volume"] >= average_volume[index]
            if new:
                states[key] = {"bar": index, "high": bar["high"], "low": bar["low"], "confirmed": False, "dead": False}
            elif key in states and not states[key]["dead"]:
                state = states[key]
                if (bar["close"] > state["high"] if bearish else bar["close"] < state["low"]):
                    state["dead"] = True
                elif not state["confirmed"] and (bar["close"] < state["low"] if bearish else bar["close"] > state["high"]):
                    state["confirmed"] = True
        row = {}
        for suffix, age in (("s",5),("l",15)):
            active = [(key, state) for key, state in states.items() if key.endswith(suffix) and not state["dead"] and index - state["bar"] <= age]
            # If both happened on the same bar Pine gives the bearish event priority.
            key, state = max(active, key=lambda item: (item[1]["bar"], item[0].startswith("bear"))) if active else (None, None)
            row["sfp_" + suffix] = (1 if state["confirmed"] else .75) * (-1 if key.startswith("bear") else 1) if state else 0.
        if pivots["bull_s"] is not None:
            last_low = index
        anchor = 60 if last_low is None else max(10, min(60, index - last_low + 6))
        profile = volume_profile(bars[max(0, index - min(anchor, index) + 1):index+1]) if index >= len(bars) - 1 - 750 else None
        if pivots["bull_s"] is not None and previous_profile is not None:
            prior_profile = previous_profile
        migration = 0.
        if profile and prior_profile:
            migration = (1. if profile["val"] > prior_profile["vah"] else -1. if profile["vah"] < prior_profile["val"] else
                         .5 if profile["poc"] > prior_profile["poc"] else -.5 if profile["poc"] < prior_profile["poc"] else 0.)
        row.update(profile=profile, prior_profile=prior_profile, migration=migration, has_prior_profile=prior_profile is not None)
        previous_profile = profile
        result.append(row)
    return result
