"""Intermarket ratios: relationships between commodities, and between
commodities and macro data (yields, inflation expectations, the dollar,
equities).

Nothing here publishes raw prices. Each ratio is published as its value,
percentile, z-score and trend (or, for ratios built on licensed inputs such as
the S&P 500, as percentile, z-score and trend only), with a rules-based reading.

Sources
  Daily  : US EIA spot prices, US Treasury / Federal Reserve rates, Fed dollar
           index (all via FRED, public domain); S&P 500 via FRED (licensed:
           used for derived statistics only).
  Monthly: World Bank Commodity Price Data ("Pink Sheet"), CC BY 4.0.
"""
from __future__ import annotations

import io
import math
import re
from datetime import date, timedelta

WB_PAGE = "https://www.worldbank.org/en/research/commodity-markets"
WB_FALLBACK = ("https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/"
               "related/CMO-Historical-Data-Monthly.xlsx")
WB_COLUMNS = {  # our key -> header text in the "Monthly Prices" sheet
    "gold": "Gold", "silver": "Silver", "copper": "Copper", "platinum": "Platinum",
    "maize": "Maize", "soybeans": "Soybeans", "wti_m": "Crude oil, WTI",
}
BU_SOY_MT = 0.0272155  # metric tons per bushel of soybeans
BU_CORN_MT = 0.0254    # metric tons per bushel of corn


# ------------------------------------------------------------------ data

def worldbank_monthly(http_get, fixture=None, log=print):
    if fixture is not None:
        import json
        raw = json.loads(fixture)
        return {k: [(date.fromisoformat(d), v) for d, v in rows] for k, rows in raw.items()}
    import pandas as pd
    url = WB_FALLBACK
    try:
        page = http_get(WB_PAGE).decode("utf-8", "ignore")
        m = re.search(r'https://thedocs\.worldbank\.org/[^"\']+CMO-Historical-Data-Monthly\.xlsx', page)
        if m:
            url = m.group(0)
    except Exception as e:
        log(f"world bank page lookup failed, using known file: {e}")
    xls = pd.read_excel(io.BytesIO(http_get(url, timeout=90)), sheet_name=None, header=None)
    sheet = next((df for name, df in xls.items() if "monthly prices" in name.lower()), None)
    if sheet is None:
        raise RuntimeError("World Bank file has no 'Monthly Prices' sheet")
    hdr = None
    for i in range(min(len(sheet), 15)):
        cells = [str(x).strip() for x in sheet.iloc[i].tolist()]
        if "Gold" in cells:
            hdr = i
            break
    if hdr is None:
        raise RuntimeError("World Bank header row not found")
    headers = [str(x).strip() for x in sheet.iloc[hdr].tolist()]
    out = {k: [] for k in WB_COLUMNS}
    cols = {}
    for k, name in WB_COLUMNS.items():
        for j, h in enumerate(headers):
            if h == name or (name == "Crude oil, WTI" and h.startswith("Crude oil, WTI")):
                cols[k] = j
                break
    for i in range(hdr + 1, len(sheet)):
        m = re.match(r"^(\d{4})M(\d{2})$", str(sheet.iat[i, 0]).strip())
        if not m:
            continue
        d = date(int(m.group(1)), int(m.group(2)), 1)
        for k, j in cols.items():
            try:
                v = float(sheet.iat[i, j])
                if not math.isnan(v) and v > 0:
                    out[k].append((d, v))
            except (TypeError, ValueError):
                pass
    if len(out.get("gold", [])) < 120:
        raise RuntimeError("World Bank parse found too little gold history")
    return out


# ------------------------------------------------------------------ math

def to_monthly(obs):
    """Average daily observations into calendar months keyed on the 1st."""
    acc = {}
    for d, v in obs:
        k = date(d.year, d.month, 1)
        s, n = acc.get(k, (0.0, 0))
        acc[k] = (s + v, n + 1)
    return sorted((k, s / n) for k, (s, n) in acc.items())


def align(a, b, fn):
    bb = dict(b)
    return [(d, fn(v, bb[d])) for d, v in a if d in bb and bb[d] not in (0, None)]


def pctile(values, v):
    return round(sum(1 for x in values if x <= v) / len(values) * 100) if values else None


def zscore(values, v):
    if len(values) < 10:
        return None
    m = sum(values) / len(values)
    sd = math.sqrt(sum((x - m) ** 2 for x in values) / (len(values) - 1))
    return round((v - m) / sd, 2) if sd else 0.0


def change_pct(series, lookback_days):
    d, v = series[-1]
    prev = None
    for dd, vv in series:
        if dd <= d - timedelta(days=lookback_days):
            prev = vv
    if prev in (None, 0):
        return None
    return round((v / prev - 1) * 100, 1)


def change_abs(series, lookback_days):
    d, v = series[-1]
    prev = None
    for dd, vv in series:
        if dd <= d - timedelta(days=lookback_days):
            prev = vv
    return None if prev is None else v - prev


def window(series, years):
    cut = series[-1][0] - timedelta(days=int(365.25 * years))
    return [v for d, v in series if d >= cut]


def downsample(series, years, max_points=260):
    cut = series[-1][0] - timedelta(days=int(365.25 * years))
    pts = [(d, v) for d, v in series if d >= cut]
    if len(pts) > max_points:
        step = math.ceil(len(pts) / max_points)
        pts = pts[::step] + ([pts[-1]] if (len(pts) - 1) % step else [])
    return pts


def returns(obs):
    return {obs[i][0]: math.log(obs[i][1] / obs[i - 1][1]) for i in range(1, len(obs))
            if obs[i - 1][1] > 0 and obs[i][1] > 0}


def diffs(obs):
    return {obs[i][0]: obs[i][1] - obs[i - 1][1] for i in range(1, len(obs))}


def corr(a: dict, b: dict, since: date):
    keys = [k for k in a if k in b and k >= since]
    if len(keys) < 60:
        return None
    x = [a[k] for k in keys]
    y = [b[k] for k in keys]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sx = math.sqrt(sum((v - mx) ** 2 for v in x))
    sy = math.sqrt(sum((v - my) ** 2 for v in y))
    if not sx or not sy:
        return None
    return round(sum((x[i] - mx) * (y[i] - my) for i in range(len(x))) / (sx * sy), 2)


# ------------------------------------------------------------------ readings

def ordinal(n):
    n = int(n)
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def trend_word(ch):
    if ch is None:
        return "flat"
    if ch > 3:
        return "rising"
    if ch < -3:
        return "falling"
    return "roughly flat"


def band(p, hi=80, lo=20):
    return "high" if p >= hi else "low" if p <= lo else "mid"


def read_ratio(key, r, ctx):
    p, t = r["pctile"], trend_word(r["chg_3m"])
    b = band(p)
    v = r.get("value")
    if key == "gold_silver":
        tag = {"high": "Defensive", "low": "Reflationary", "mid": "Neutral"}[b]
        txt = f"An ounce of gold buys {v:.0f} ounces of silver, the {ordinal(p)} percentile of the past {r['years']} years and {t} over 3 months. "
        txt += {"high": "Investors are favoring the haven metal over the industrial one.",
                "low": "Silver is outperforming, a sign of industrial demand and risk appetite.",
                "mid": "Neither haven demand nor industrial demand dominates."}[b]
    elif key == "copper_gold":
        tag = {"high": "Growth", "low": "Growth scare", "mid": "Neutral"}[b]
        txt = f"Copper relative to gold is at the {ordinal(p)} percentile of {r['years']} years and {t} over 3 months. "
        txt += {"high": "Markets are pricing industrial growth ahead of safety.",
                "low": "Safety is being priced ahead of growth.",
                "mid": "Growth and safety demand are roughly balanced."}[b]
        y3 = ctx.get("t10_chg_3m")
        if y3 is not None and r["chg_3m"] is not None and abs(r["chg_3m"]) > 3 and (y3 > 0) != (r["chg_3m"] > 0):
            txt += f" The 10-year yield has moved the other way ({y3 * 100:+.0f} bp in 3 months), a divergence that usually closes with one catching up to the other."
    elif key == "gold_oil":
        tag = {"high": "Growth fears", "low": "Energy-led inflation", "mid": "Neutral"}[b]
        txt = f"An ounce of gold buys {v:.1f} barrels of WTI, the {ordinal(p)} percentile of {r['years']} years and {t} over 3 months. "
        txt += {"high": "Gold is expensive against oil, typical of haven demand or weak energy demand.",
                "low": "Oil is expensive against gold, typical of energy-led inflation pressure.",
                "mid": "The relationship is in its normal range."}[b]
    elif key == "oil_gas":
        tag = {"high": "Gas cheap vs oil", "low": "Gas rich vs oil", "mid": "Neutral"}[b]
        txt = f"A barrel of WTI costs {v:.1f} times an MMBtu of Henry Hub gas (energy parity is about 5.8), the {ordinal(p)} percentile of {r['years']} years. "
        txt += {"high": "US gas is cheap relative to crude, which supports gas-fired power and LNG export margins.",
                "low": "Gas is expensive relative to crude, which squeezes gas-intensive industry.",
                "mid": "The oil-to-gas relationship is in its normal range."}[b]
    elif key == "brent_wti":
        tag = {"high": "Seaborne tightness", "low": "US tightness", "mid": "Neutral"}[b]
        txt = f"Brent trades at a {abs(v):.1f}% {'premium' if v >= 0 else 'discount'} to WTI, the {ordinal(p)} percentile of {r['years']} years. "
        txt += {"high": "A wide spread points to tight international supply relative to the US market.",
                "low": "A narrow spread points to a tight US market or strong US export demand.",
                "mid": "The transatlantic spread is in its normal range."}[b]
    elif key == "crack":
        tag = {"high": "Strong margins", "low": "Weak demand", "mid": "Neutral"}[b]
        txt = f"Refined products in New York Harbor are worth {v:.0f}% more than the crude they're made from (3-2-1 crack), the {ordinal(p)} percentile of {r['years']} years. "
        txt += {"high": "Refiners are earning strong margins, a sign of firm fuel demand or tight refining capacity.",
                "low": "Refining margins are thin, a sign of soft fuel demand.",
                "mid": "Refining margins are in their normal range."}[b]
    elif key == "soy_corn":
        tag = "Favors soybeans" if v >= 2.5 else "Favors corn" if v <= 2.2 else "Neutral"
        txt = f"Soybeans are priced at {v:.2f} times corn per bushel ({ordinal(p)} percentile of {r['years']} years). "
        txt += ("Above 2.5, growers tend to shift acreage to soybeans." if v >= 2.5 else
                "Below 2.2, growers tend to shift acreage to corn." if v <= 2.2 else
                "Neither crop has a clear planting advantage.")
    elif key == "spx_gold":
        tag = {"high": "Equities rich vs gold", "low": "Gold outperforming", "mid": "Neutral"}[b]
        txt = f"The S&P 500 priced in gold is at the {ordinal(p)} percentile of {r['years']} years and {t} over 3 months. "
        txt += {"high": "Equities are expensive against real assets.",
                "low": "Gold has been outperforming equities, typical of defensive or inflationary periods.",
                "mid": "Equities and gold are in their usual relationship."}[b]
    elif key == "spx_oil":
        tag = {"high": "Equities rich vs energy", "low": "Energy outperforming", "mid": "Neutral"}[b]
        txt = f"The S&P 500 priced in barrels of WTI is at the {ordinal(p)} percentile of {r['years']} years and {t} over 3 months. "
        txt += {"high": "Financial assets are expensive against energy.",
                "low": "Energy has been outperforming equities.",
                "mid": "Equities and energy are in their usual relationship."}[b]
    else:
        tag, txt = "Neutral", ""
    return tag, txt


# ------------------------------------------------------------------ build

def build(fred, http_get, wb_fixture=None, log=print):
    today = date.today()
    D = {}
    for k, s in {"wti": "DCOILWTICO", "brent": "DCOILBRENTEU", "hh": "DHHNGSP", "gas_nyh": "DGASNYH",
                 "ho_nyh": "DHOILNYH", "t10": "DGS10", "real": "DFII10", "be": "T10YIE",
                 "usd": "DTWEXBGS", "spx": "SP500"}.items():
        try:
            D[k] = fred(s, years=11)
        except Exception as e:
            log(f"[intermarket {k}] {e}")
    try:
        WB = worldbank_monthly(http_get, wb_fixture, log)
    except Exception as e:
        log(f"[intermarket world bank] {e}")
        WB = {}

    ctx = {}
    if "t10" in D:
        ctx["t10_chg_3m"] = change_abs(D["t10"], 91)

    specs = []  # (key, name, pair, group, freq, license, series, years_for_stats, unit)
    def add(key, name, pair, group, freq, lic, series, yrs, unit=""):
        if series and len(series) > 24:
            specs.append((key, name, pair, group, freq, lic, series, yrs, unit))

    if WB.get("gold") and WB.get("silver"):
        add("gold_silver", "Gold / Silver", "oz silver per oz gold", "Metals", "Monthly", "public",
            align(WB["gold"], WB["silver"], lambda a, b: a / b), 20)
    if WB.get("copper") and WB.get("gold"):
        add("copper_gold", "Copper / Gold", "copper $/lb ÷ gold $/oz, growth vs safety", "Metals", "Monthly", "public",
            align(WB["copper"], WB["gold"], lambda a, b: a / 2204.62 / b * 1000), 20, "×1000")
    oil_m = WB.get("wti_m") or (to_monthly(D["wti"]) if "wti" in D else None)
    if WB.get("gold") and oil_m:
        add("gold_oil", "Gold / Oil", "barrels of WTI per oz gold", "Cross-commodity", "Monthly", "public",
            align(WB["gold"], oil_m, lambda a, b: a / b), 20)
    if "wti" in D and "hh" in D:
        add("oil_gas", "Oil / Natural gas", "WTI $/bbl ÷ Henry Hub $/MMBtu", "Energy", "Daily", "public",
            align(D["wti"], D["hh"], lambda a, b: a / b), 10)
    if "wti" in D and "brent" in D:
        add("brent_wti", "Brent vs WTI", "Brent premium over WTI, %", "Energy", "Daily", "public",
            align(D["brent"], D["wti"], lambda a, b: (a / b - 1) * 100), 10, "%")
    if all(k in D for k in ("gas_nyh", "ho_nyh", "wti")):
        prod = align(D["gas_nyh"], D["ho_nyh"], lambda g, h: (2 * g + h) / 3 * 42)
        add("crack", "3-2-1 crack spread", "refining margin as % of crude cost", "Energy", "Daily", "public",
            align(prod, D["wti"], lambda p, w: (p / w - 1) * 100), 10, "%")
    if WB.get("soybeans") and WB.get("maize"):
        add("soy_corn", "Soybeans / Corn", "price per bushel", "Agriculture", "Monthly", "public",
            align(WB["soybeans"], WB["maize"], lambda s, c: (s * BU_SOY_MT) / (c * BU_CORN_MT)), 20)
    if "spx" in D and WB.get("gold"):
        add("spx_gold", "S&P 500 / Gold", "equities priced in gold", "Equities vs commodities", "Monthly", "restricted",
            align(to_monthly(D["spx"]), WB["gold"], lambda a, b: a / b), 10)
    if "spx" in D and "wti" in D:
        add("spx_oil", "S&P 500 / Oil", "equities priced in barrels", "Equities vs commodities", "Daily", "restricted",
            align(D["spx"], D["wti"], lambda a, b: a / b), 10)

    ratios = []
    for key, name, pair, group, freq, lic, s, yrs, unit in specs:
        hist_window = window(s, yrs)
        d, v = s[-1]
        z_window = window(s, 5)
        lookback = 91
        r = dict(key=key, name=name, pair=pair, group=group, freq=freq, license=lic,
                 asOf=d.isoformat(), pctile=pctile(hist_window, v), z5=zscore(z_window, v),
                 chg_3m=change_pct(s, lookback), chg_1y=change_pct(s, 365), years=yrs, unit=unit)
        if key in ("brent_wti", "crack"):
            r["chg_3m"] = round(change_abs(s, lookback) or 0, 1)
            r["chg_1y"] = round(change_abs(s, 365) or 0, 1)
        r["value"] = round(v, 4)
        tag, txt = read_ratio(key, r, ctx)
        r["tag"], r["read"] = tag, txt
        pts = downsample(s, min(yrs, 10 if freq == "Daily" else 20))
        hw = sorted(hist_window)
        r["p10"] = round(hw[int(len(hw) * 0.1)], 4)
        r["p90"] = round(hw[min(len(hw) - 1, int(len(hw) * 0.9))], 4)
        if lic == "restricted":
            # Publish derived statistics only: rolling 5-year z-score history, no ratio level.
            zs = []
            for i, (dd, vv) in enumerate(pts):
                base = [x for (x_d, x) in s if dd - timedelta(days=int(365.25 * 5)) <= x_d <= dd]
                z = zscore(base, vv)
                if z is not None:
                    zs.append([dd.isoformat(), z])
            r["history"] = zs
            r["history_kind"] = "z"
            r.pop("value")
            r.pop("p10")
            r.pop("p90")
            r["read"] = re.sub(r"\s+", " ", r["read"])
        else:
            r["history"] = [[dd.isoformat(), round(vv, 4)] for dd, vv in pts]
            r["history_kind"] = "level"
        ratios.append(r)

    # relationships between commodities and macro (rolling 1-year correlations of daily changes)
    since = today - timedelta(days=365)
    series_for_corr = {
        "WTI": returns(D["wti"]) if "wti" in D else None,
        "Nat gas": returns(D["hh"]) if "hh" in D else None,
        "10Y yield": diffs(D["t10"]) if "t10" in D else None,
        "Real yield": diffs(D["real"]) if "real" in D else None,
        "Breakeven": diffs(D["be"]) if "be" in D else None,
        "US dollar": returns(D["usd"]) if "usd" in D else None,
        "S&P 500": returns(D["spx"]) if "spx" in D else None,
    }
    names = [k for k, v in series_for_corr.items() if v]
    matrix = [[1.0 if a == b else corr(series_for_corr[a], series_for_corr[b], since) for b in names] for a in names]

    links = []
    def link(a, b, label, strong_pos, strong_neg, normal):
        if a in names and b in names:
            c = matrix[names.index(a)][names.index(b)]
            if c is None:
                return
            if c >= 0.35:
                txt = strong_pos
            elif c <= -0.35:
                txt = strong_neg
            else:
                txt = normal
            links.append(dict(pair=f"{a} ↔ {b}", label=label, corr=c, read=txt))
    link("WTI", "Breakeven", "Oil and inflation expectations",
         "Oil is driving inflation expectations: moves in crude are passing through to breakevens.",
         "Unusually, oil and inflation expectations are moving in opposite directions.",
         "Inflation expectations are not closely tracking oil right now.")
    link("WTI", "US dollar", "Oil and the dollar",
         "Oil and the dollar are rising together, a sign that supply, not the currency, is setting the oil price.",
         "The classic link holds: a weaker dollar supports oil prices, a stronger one weighs on them.",
         "The dollar is having little day-to-day effect on oil.")
    link("S&P 500", "10Y yield", "Equities and bond yields",
         "Stocks rise when yields rise: markets are reading higher yields as stronger growth.",
         "Stocks fall when yields rise: higher rates are hurting equity valuations.",
         "Equities are not reacting consistently to yield moves.")
    link("WTI", "S&P 500", "Oil and equities",
         "Oil and equities are moving together, typical when growth expectations drive both.",
         "Oil and equities are moving in opposite directions, typical of a supply shock.",
         "Oil and equities are moving independently.")

    # cross-asset read
    by = {r["key"]: r for r in ratios}
    score, notes = 0, []
    def sig(key, up_is_growth=True, w=1):
        nonlocal score
        r = by.get(key)
        if not r or r.get("chg_3m") is None:
            return
        ch = r["chg_3m"]
        if abs(ch) < 3 and key not in ("brent_wti", "crack"):
            return
        s = (1 if ch > 0 else -1) * (1 if up_is_growth else -1) * w
        score += s
    sig("copper_gold", True, 2)
    sig("gold_silver", False)
    sig("spx_gold", True)
    sig("gold_oil", False)
    extremes = sorted([r for r in ratios if r["pctile"] is not None and (r["pctile"] >= 85 or r["pctile"] <= 15)],
                      key=lambda r: -abs(r["pctile"] - 50))
    for r in extremes[:4]:
        tag = "" if r["tag"] == "Neutral" else f" ({r['tag'].lower()})"
        notes.append(f"{r['name']} is at the {ordinal(r['pctile'])} percentile{tag}.")
    oil_be = next((l for l in links if l["label"].startswith("Oil and inflation")), None)
    inflationary = oil_be and oil_be["corr"] >= 0.35 and (by.get("gold_oil", {}).get("pctile", 50) <= 35)
    if score >= 2:
        regime = "Reflationary"
        line = "Ratios lean toward growth: industrial metals and equities are gaining on gold."
    elif score <= -2:
        regime = "Defensive"
        line = "Ratios lean defensive: gold is gaining on industrial metals and equities."
    else:
        regime = "Mixed"
        line = "Signals are mixed: no single growth or safety theme dominates the ratios."
    if inflationary:
        line += " Oil is also feeding inflation expectations."
    read = dict(regime=regime, line=line, notes=notes, score=score)

    return dict(ratios=ratios, correlations=dict(names=names, matrix=matrix, window="1 year, daily changes"),
                links=links, read=read)
