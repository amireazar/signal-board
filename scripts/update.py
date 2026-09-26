#!/usr/bin/env python3
"""Build site/data/indicators.json for the Analytica Horizon Market Signal Board.

Pulls public-domain series (FRED, US Treasury Fiscal Data, CFTC, FINRA),
merges hand-maintained readings from config/manual.json, scores each
indicator (bear / watch / bull / na), and records status changes since the
last published build.

Environment:
  FRED_API_KEY   free key from https://fred.stlouisfed.org/docs/api/api_key.html
  AH_FIXTURES    optional folder of saved responses for offline testing
  AH_PREVIOUS    optional path or URL of the previously published indicators.json
"""
from __future__ import annotations

import io
import json
import math
import os
import re
import sys
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config" / "indicators.json").read_text())
MANUAL = json.loads((ROOT / "config" / "manual.json").read_text())
OUT = ROOT / "site" / "data" / "indicators.json"
FIX = os.environ.get("AH_FIXTURES")
UA = {"User-Agent": "AnalyticaHorizon-SignalBoard/1.0 (+https://analyticahorizon.com)"}
TODAY = date.today()
LOG: list[str] = []


def log(msg: str) -> None:
    LOG.append(msg)
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------- fetching

def _fixture(name: str):
    p = Path(FIX) / name
    if not p.exists():
        raise FileNotFoundError(f"fixture missing: {name}")
    return p.read_bytes()


def http_get(url: str, params: dict | None = None, timeout: int = 45) -> bytes:
    r = requests.get(url, params=params, headers=UA, timeout=timeout)
    r.raise_for_status()
    return r.content


_fred_cache: dict[str, list[tuple[date, float]]] = {}


def fred(series: str, years: int = 3) -> list[tuple[date, float]]:
    """Observations as [(date, value)], oldest first, missing values dropped."""
    key = f"{series}:{years}"
    if key in _fred_cache:
        return _fred_cache[key]
    if FIX:
        raw = json.loads(_fixture(f"fred_{series}.json"))
    else:
        api_key = os.environ.get("FRED_API_KEY")
        if not api_key:
            raise RuntimeError("FRED_API_KEY is not set")
        start = (TODAY - timedelta(days=365 * years + 30)).isoformat()
        raw = json.loads(http_get(
            "https://api.stlouisfed.org/fred/series/observations",
            {"series_id": series, "api_key": api_key, "file_type": "json", "observation_start": start},
        ))
    obs = []
    for o in raw.get("observations", []):
        v = o.get("value")
        if v in (None, ".", ""):
            continue
        try:
            obs.append((date.fromisoformat(o["date"]), float(v)))
        except ValueError:
            continue
    if not obs:
        raise RuntimeError(f"no observations for {series}")
    _fred_cache[key] = obs
    return obs


def finra_margin() -> list[dict]:
    """Monthly FINRA margin statistics since 1997: date, debit, cash_free, margin_free ($ millions)."""
    if FIX:
        rows = json.loads(_fixture("finra.json"))
        return [dict(r, date=date.fromisoformat(r["date"])) for r in rows]
    import pandas as pd

    page = "https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics"
    url = "https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx"
    try:
        html = http_get(page).decode("utf-8", "ignore")
        m = re.search(r'href="([^"]*margin[^"]*\.xlsx)"', html, re.I)
        if m:
            url = m.group(1) if m.group(1).startswith("http") else "https://www.finra.org" + m.group(1)
    except Exception as e:  # fall back to the known path
        log(f"finra page lookup failed, using default file: {e}")
    xls = pd.read_excel(io.BytesIO(http_get(url)), sheet_name=None, header=None)

    rows: dict[date, dict] = {}
    for _, df in xls.items():
        hdr_row = None
        for i in range(min(len(df), 15)):
            cells = " | ".join(str(x) for x in df.iloc[i].tolist())
            if "Debit" in cells:
                hdr_row = i
                break
        if hdr_row is None:
            continue
        headers = [str(x).strip() for x in df.iloc[hdr_row].tolist()]

        def col(pred):
            for j, h in enumerate(headers):
                if pred(h.lower()):
                    return j
            return None

        c_debit = col(lambda h: "debit" in h)
        c_cash = col(lambda h: "free credit" in h and "cash" in h)
        c_marg = col(lambda h: "free credit" in h and "margin" in h)
        c_date = col(lambda h: "month" in h or "date" in h or "year" in h)
        if c_date is None:
            c_date = 0
        for i in range(hdr_row + 1, len(df)):
            raw_d = df.iat[i, c_date]
            d = _parse_month(raw_d)
            if d is None:
                continue
            try:
                debit = float(df.iat[i, c_debit])
            except (TypeError, ValueError):
                continue
            if math.isnan(debit):
                continue
            rec = {"date": d, "debit": debit}
            for k, c in (("cash_free", c_cash), ("margin_free", c_marg)):
                try:
                    v = float(df.iat[i, c]) if c is not None else float("nan")
                    rec[k] = None if math.isnan(v) else v
                except (TypeError, ValueError):
                    rec[k] = None
            rows[d] = rec
    if len(rows) < 24:
        raise RuntimeError(f"FINRA parse found only {len(rows)} months; the file layout may have changed")
    return [rows[k] for k in sorted(rows)]


def _parse_month(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        return date(v.year, v.month, 1)
    try:
        import pandas as pd
        if isinstance(v, pd.Timestamp):
            return date(v.year, v.month, 1)
    except Exception:
        pass
    s = str(v).strip()
    for fmt in ("%b-%y", "%b-%Y", "%B-%y", "%B %Y", "%b %Y", "%Y-%m", "%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s, fmt)
            return date(d.year, d.month, 1)
        except ValueError:
            continue
    return None


def auctions() -> list[dict]:
    if FIX:
        return json.loads(_fixture("auctions.json"))
    base = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query"
    out = []
    for kind in ("Note", "Bond"):
        raw = json.loads(http_get(base, {
            "filter": f"security_type:eq:{kind}",
            "sort": "-auction_date",
            "page[size]": "40",
        }))
        out += raw.get("data", [])
    return out


def cftc_es() -> list[dict]:
    if FIX:
        return json.loads(_fixture("cftc.json"))
    # Traders in Financial Futures, futures only (CFTC public reporting environment)
    url = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
    raw = json.loads(http_get(url, {
        "$where": "market_and_exchange_names like 'E-MINI S&P 500 -%'",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": "160",
    }))
    return raw


# ---------------------------------------------------------------- helpers

def last(obs):
    return obs[-1]


def value_at_or_before(obs, d: date):
    best = None
    for od, v in obs:
        if od <= d:
            best = (od, v)
        else:
            break
    return best


def pct(a, b):
    return (a / b - 1) * 100


def fmt(v, dp=2, units=""):
    s = f"{v:,.{dp}f}"
    return s.replace("-", "−") + units


def history(obs, years=2, max_points=160):
    cut = TODAY - timedelta(days=365 * years)
    pts = [(d, v) for d, v in obs if d >= cut]
    if len(pts) > max_points:
        step = math.ceil(len(pts) / max_points)
        pts = pts[::step] + ([pts[-1]] if (len(pts) - 1) % step else [])
    return [[d.isoformat(), round(v, 4)] for d, v in pts]


def period_end(obs) -> str:
    """Report monthly/quarterly observations at the end of their period (FRED dates them at the start)."""
    d = obs[-1][0]
    gap = (obs[-1][0] - obs[-2][0]).days if len(obs) > 1 else 1
    if gap >= 80:
        q_end_month = ((d.month - 1) // 3 + 1) * 3
        return _month_end(date(d.year, q_end_month, 1))
    if gap >= 25:
        return _month_end(d)
    return d.isoformat()


def change_note(delta, dp, kind, span):
    if kind == "bp":
        bp = round(abs(delta) * 100)
        return f"Unchanged {span}" if bp == 0 else f"{'Up' if delta > 0 else 'Down'} {bp} bp {span}"
    if round(abs(delta), dp) == 0:
        return f"Unchanged {span}"
    return f"{'Up' if delta > 0 else 'Down'} {fmt(abs(delta), dp)}{' pts' if kind == 'pts' else ''} {span}"


def level_status(v, bear, watch):
    """Higher is worse."""
    if v >= bear:
        return "bear"
    if v >= watch:
        return "watch"
    return "bull"


# ---------------------------------------------------------------- calculators
# Each returns dict(reading, status, asOf, note, history?)

def calc_level(ind):
    obs = fred(ind["fred"])
    d, v = last(obs)
    st = level_status(v, ind["bear"], ind["watch"])
    dp, units = ind.get("dp", 2), ind.get("units", "")
    gap = (obs[-1][0] - obs[-2][0]).days if len(obs) > 1 else 1
    if gap >= 25:
        ch, span = v - obs[-2][1], "from the previous reading"
    else:
        prev = value_at_or_before(obs, d - timedelta(days=30))
        ch, span = (v - prev[1]) if prev else 0, "over the past month"
    note = change_note(ch, dp, ind.get("chg", ""), span)
    return dict(reading=fmt(v, dp, units), status=st, asOf=period_end(obs),
                note=note, history=history(obs))


def calc_tp(ind):
    obs = fred(ind["fred"])
    d, v = last(obs)
    p = value_at_or_before(obs, d - timedelta(days=60))
    ch = v - p[1] if p else 0
    st = "bear" if (v >= 1.25 or ch >= 0.25) else ("watch" if v >= 0.5 else "bull")
    return dict(reading=fmt(v, 2, "%"), status=st, asOf=d.isoformat(),
                note=f"{'+' if ch >= 0 else '−'}{abs(ch) * 100:.0f} bp over 60 days", history=history(obs))


def calc_fed(ind):
    obs = fred(ind["fred"])
    d, v = last(obs)
    p = value_at_or_before(obs, d - timedelta(days=90))
    ch = v - p[1] if p else 0
    t10 = fred("DGS10")
    t_now = last(t10)[1]
    t_prev = value_at_or_before(t10, d - timedelta(days=90))
    t_ch = t_now - t_prev[1] if t_prev else 0
    if ch >= 0.25:
        st, note = "bear", "Fed has been raising rates"
    elif ch <= -0.25 and t_ch <= 0:
        st, note = "bull", "Fed is cutting and long yields are falling too"
    elif ch <= -0.25:
        st, note = "watch", f"Fed is cutting, but the 10-year is up {t_ch * 100:.0f} bp over 90 days"
    else:
        st, note = "watch", "Policy rate roughly unchanged over 90 days"
    return dict(reading=fmt(v, 2, "%"), status=st, asOf=d.isoformat(), note=note, history=history(obs))


def calc_bs(ind):
    obs = fred(ind["fred"])
    d, v = last(obs)
    p = value_at_or_before(obs, d - timedelta(weeks=13))
    ch = pct(v, p[1]) if p else 0
    st = "bear" if ch < -1 else ("bull" if ch > 1 else "watch")
    return dict(reading=f"${v / 1e6:,.2f}T", status=st, asOf=d.isoformat(),
                note=f"{'+' if ch >= 0 else '−'}{abs(ch):.1f}% over 13 weeks", history=history(obs))


def calc_curve(ind):
    obs = fred(ind["fred"])
    d, v = last(obs)
    recent_min = min(x for dd, x in obs if dd >= d - timedelta(days=730))
    if v < 0:
        st, note = "watch", "Inverted"
    elif recent_min < 0:
        st, note = "watch", "Recently un-inverted, a pattern that has often come before recessions"
    else:
        st, note = "bull", "Upward sloping"
    return dict(reading=fmt(v, 2, " pts"), status=st, asOf=d.isoformat(), note=note, history=history(obs))


def calc_usd(ind):
    obs = fred(ind["fred"])
    d, v = last(obs)
    p = value_at_or_before(obs, d - timedelta(days=91))
    ch = pct(v, p[1]) if p else 0
    st = "bear" if ch > 5 else ("bull" if ch < -3 else "watch")
    return dict(reading=fmt(v, 1), status=st, asOf=d.isoformat(),
                note=f"{'+' if ch >= 0 else '−'}{abs(ch):.1f}% over 3 months", history=history(obs))


def calc_delinq(ind):
    obs = fred(ind["fred"], years=4)
    d, v = last(obs)
    p = value_at_or_before(obs, d - timedelta(days=365))
    ch = v - p[1] if p else 0
    st = "bear" if ch >= 0.3 else ("watch" if ch > 0 else "bull")
    return dict(reading=fmt(v, 2, "%"), status=st, asOf=period_end(obs),
                note=f"{'Up' if ch >= 0 else 'Down'} {abs(ch):.2f} pts from a year earlier", history=history(obs, 4))


def calc_claims(ind):
    obs = fred(ind["fred"])
    avg4 = []
    for i in range(3, len(obs)):
        avg4.append((obs[i][0], sum(x for _, x in obs[i - 3:i + 1]) / 4))
    d, v = avg4[-1]
    low = min(x for dd, x in avg4 if dd >= d - timedelta(days=365))
    up = pct(v, low)
    st = "bear" if up >= 20 else ("watch" if up >= 10 else "bull")
    return dict(reading=f"{obs[-1][1] / 1000:,.0f}K", status=st, asOf=obs[-1][0].isoformat(),
                note=f"4-week average {v / 1000:,.0f}K, {up:.0f}% above its 1-year low", history=history(obs))


def calc_oil(ind):
    obs = fred(ind["fred"])
    d, v = last(obs)
    p = value_at_or_before(obs, d - timedelta(days=365))
    ch = pct(v, p[1]) if p else 0
    st = "bear" if (v > 100 or ch > 30) else ("watch" if (v > 85 or ch > 10) else "bull")
    return dict(reading=f"${v:,.2f}", status=st, asOf=d.isoformat(),
                note=f"{'+' if ch >= 0 else '−'}{abs(ch):.0f}% from a year earlier", history=history(obs))


def calc_infl(ind):
    core, head = fred(ind["fred"], 4), fred(ind["fred2"], 4)

    def yoy(obs):
        d, v = last(obs)
        p = value_at_or_before(obs, date(d.year - 1, d.month, 1))
        return d, pct(v, p[1])

    d, c = yoy(core)
    _, h = yoy(head)
    m3 = d.month - 3
    p3 = value_at_or_before(core, date(d.year + (m3 - 1) // 12, (m3 - 1) % 12 + 1, 1))
    ann3 = ((core[-1][1] / p3[1]) ** 4 - 1) * 100 if p3 else float("nan")
    st = "bear" if (c >= 3.5 or h >= 4) else ("watch" if (c >= 2.75 or h >= 3) else "bull")
    hist = []
    for dd, v in core:
        p = value_at_or_before(core, date(dd.year - 1, dd.month, 1))
        if p and dd >= TODAY - timedelta(days=730):
            hist.append([dd.isoformat(), round(pct(v, p[1]), 2)])
    return dict(reading=f"CPI {h:.1f}% · core {c:.1f}%", status=st, asOf=period_end(core),
                note=f"Core 3-month annualized {ann3:.1f}%", history=hist)


def calc_mmf(ind):
    obs = fred(ind["fred"], 3)
    d, v = last(obs)
    p = value_at_or_before(obs, d - timedelta(days=365))
    ch = pct(v, p[1]) if p else 0
    st = "bull" if ch > 0 else "watch"
    return dict(reading=f"${v / 1e6:,.2f}T", status=st, asOf=period_end(obs),
                note=f"{'+' if ch >= 0 else '−'}{abs(ch):.0f}% from a year earlier; Fed Z.1, quarter-end", history=history(obs, 3))


_finra = None


def finra():
    global _finra
    if _finra is None:
        _finra = finra_margin()
    return _finra


def _md_yoy_series(rows):
    by = {r["date"]: r for r in rows}
    out = []
    for r in rows:
        p = by.get(date(r["date"].year - 1, r["date"].month, 1))
        if p:
            out.append((r["date"], pct(r["debit"], p["debit"])))
    return out


def calc_md_yoy(ind):
    rows = finra()
    s = _md_yoy_series(rows)
    d, v = s[-1]
    peak = max(s, key=lambda x: x[1] if x[0] >= d - timedelta(days=730) else -1e9)
    st = "bear" if v >= 30 else ("watch" if v >= 15 else "bull")
    return dict(reading=f"{'+' if v >= 0 else '−'}{abs(v):.1f}%", status=st, asOf=_month_end(d),
                note=f"Debit balances ${rows[-1]['debit'] / 1e6:,.2f}T; 2-yr peak growth {peak[1]:+.1f}% ({peak[0]:%b %Y})",
                history=[[a.isoformat(), round(b, 2)] for a, b in s if a >= d - timedelta(days=730)])


def calc_md_gdp(ind):
    rows = finra()
    gdp = fred("GDP", years=40)
    s = []
    for r in rows:
        g = value_at_or_before(gdp, r["date"])
        if g:
            s.append((r["date"], r["debit"] / 1000 / g[1] * 100))  # debit $M -> $B; GDP $B SAAR
    d, v = s[-1]
    vals = sorted(x for _, x in s)
    rank = sum(1 for x in vals if x <= v) / len(vals) * 100
    st = "bear" if rank >= 90 else ("watch" if rank >= 70 else "bull")
    return dict(reading=f"{v:.2f}% of GDP", status=st, asOf=_month_end(d),
                note=f"{rank:.0f}th percentile since {s[0][0].year}",
                history=[[a.isoformat(), round(b, 3)] for a, b in s if a >= d - timedelta(days=730)])


def calc_md_cash(ind):
    rows = [r for r in finra() if r.get("cash_free") is not None and r.get("margin_free") is not None]
    s = [(r["date"], (r["cash_free"] + r["margin_free"]) / r["debit"] * 100) for r in rows]
    d, v = s[-1]
    p = value_at_or_before(s, date(d.year - 1, d.month, 1))
    ch = v - p[1] if p else 0
    st = "bear" if (v < 30 and ch < 0) else ("watch" if ch < 0 else "bull")
    return dict(reading=f"{v:.1f}%", status=st, asOf=_month_end(d),
                note=f"{'Up' if ch >= 0 else 'Down'} {abs(ch):.1f} pts from a year earlier",
                history=[[a.isoformat(), round(b, 2)] for a, b in s if a >= d - timedelta(days=730)])


def _month_end(d: date) -> str:
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return (nxt - timedelta(days=1)).isoformat()


def calc_auctions(ind):
    data = auctions()

    def pick(pred):
        xs = [r for r in data if pred(r) and str(r.get("inflation_index_security", "No")).lower() != "yes"
              and r.get("bid_to_cover_ratio") not in (None, "", "null")]
        xs.sort(key=lambda r: r["auction_date"], reverse=True)
        return xs[0] if xs else None

    ten = pick(lambda r: str(r.get("security_term", "")).startswith(("10-Year", "9-Year 1")))
    thirty = pick(lambda r: str(r.get("security_term", "")).startswith(("30-Year", "29-Year")))
    if not ten:
        raise RuntimeError("no recent 10-year auction found")
    b10 = float(ten["bid_to_cover_ratio"])
    st = "bear" if b10 < 2.3 else ("watch" if b10 < 2.45 else "bull")
    parts = [f"10-yr {b10:.2f}x"]
    note = f"10-yr cleared at {float(ten['high_yield']):.3f}% on {ten['auction_date']}"
    if thirty:
        parts.append(f"30-yr {float(thirty['bid_to_cover_ratio']):.2f}x")
        note += f"; 30-yr at {float(thirty['high_yield']):.3f}% on {thirty['auction_date']}"
    return dict(reading=" · ".join(parts), status=st, asOf=ten["auction_date"], note=note + ". Bid-to-cover shown.")


def calc_cot(ind):
    rows = cftc_es()
    recs = []
    for r in rows:
        try:
            oi = float(r["open_interest_all"])
            am = float(r["asset_mgr_positions_long"]) - float(r["asset_mgr_positions_short"])
            lev = float(r["lev_money_positions_long"]) - float(r["lev_money_positions_short"])
            d = date.fromisoformat(r["report_date_as_yyyy_mm_dd"][:10])
            recs.append((d, am, lev, am / oi * 100))
        except (KeyError, ValueError, ZeroDivisionError):
            continue
    if not recs:
        raise RuntimeError("no E-mini S&P rows in CFTC response")
    recs.sort()
    d, am, lev, share = recs[-1]
    window = [x[3] for x in recs if x[0] >= d - timedelta(days=365 * 3)]
    rank = sum(1 for x in window if x <= share) / len(window) * 100
    st = "bear" if rank >= 90 else ("watch" if rank >= 75 else "bull")
    return dict(reading=f"Asset managers net long {am / 1000:,.0f}K", status=st, asOf=d.isoformat(),
                note=f"{share:.0f}% of open interest, {rank:.0f}th percentile of 3 years; leveraged funds net {'long' if lev >= 0 else 'short'} {abs(lev) / 1000:,.0f}K",
                history=[[x[0].isoformat(), round(x[3], 2)] for x in recs if x[0] >= d - timedelta(days=730)])


CALCS = {
    "level": calc_level, "tp": calc_tp, "fed": calc_fed, "bs": calc_bs, "curve": calc_curve, "usd": calc_usd,
    "delinq": calc_delinq, "claims": calc_claims, "oil": calc_oil, "infl": calc_infl, "mmf": calc_mmf,
    "md_yoy": calc_md_yoy, "md_gdp": calc_md_gdp, "md_cash": calc_md_cash,
    "auctions": calc_auctions, "cot": calc_cot,
}


# ---------------------------------------------------------------- charts

def margin_charts():
    rows = finra()
    gdp = fred("GDP", years=40)
    by = {r["date"]: r for r in rows}
    labels, debit, yoy, cash, mdgdp = [], [], [], [], []
    for r in rows:
        labels.append(r["date"].strftime("%Y-%m"))
        debit.append(round(r["debit"] / 1000, 1))
        p = by.get(date(r["date"].year - 1, r["date"].month, 1))
        yoy.append(round(pct(r["debit"], p["debit"]), 1) if p else None)
        cf, mf = r.get("cash_free"), r.get("margin_free")
        cash.append(round((cf + mf) / r["debit"] * 100, 1) if cf is not None and mf is not None else None)
        g = value_at_or_before(gdp, r["date"])
        mdgdp.append(round(r["debit"] / 1000 / g[1] * 100, 2) if g else None)
    return dict(labels=labels, debit_bn=debit, yoy=yoy, cash_pct=cash, md_gdp=mdgdp)


# ---------------------------------------------------------------- previous build

def load_previous():
    src = os.environ.get("AH_PREVIOUS") or (CFG["site"]["url"].rstrip("/") + "/data/indicators.json")
    try:
        if src.startswith("http"):
            if FIX:
                return None
            return json.loads(http_get(src, timeout=20))
        p = Path(src)
        return json.loads(p.read_text()) if p.exists() else None
    except Exception as e:
        log(f"no previous build available ({e}); change log starts fresh")
        return None


# ---------------------------------------------------------------- main

def main() -> int:
    prev = load_previous()
    prev_by = {x["id"]: x for x in (prev or {}).get("indicators", [])}
    show_restricted = bool(CFG["site"].get("show_restricted_values"))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    out = []
    failures = 0
    for ind in CFG["indicators"]:
        base = {k: ind[k] for k in ("id", "cat", "name", "role", "rule", "mode", "license", "source")}
        try:
            if ind["mode"] == "auto":
                r = CALCS[ind["calc"]](ind)
                r["stale"] = False
            else:
                m = MANUAL.get(ind["id"], {})
                restricted = ind["license"] == "restricted" and not show_restricted
                r = dict(
                    reading="" if restricted else m.get("reading", ""),
                    status=m.get("status") or "na",
                    asOf=m.get("asOf", ""),
                    note=m.get("public_note", "") if restricted else (m.get("note") or m.get("public_note", "")),
                    stale=False,
                    hidden_value=restricted and bool(m.get("reading")),
                )
        except Exception as e:
            failures += 1
            log(f"[{ind['id']}] failed: {e}")
            if os.environ.get("AH_DEBUG"):
                traceback.print_exc()
            old = prev_by.get(ind["id"])
            if old:
                r = {k: old.get(k) for k in ("reading", "status", "asOf", "note", "history")}
                r["stale"] = True
            else:
                r = dict(reading="", status="na", asOf="", note="Data source unavailable on the last update", stale=True)
        if r.get("status") not in ("bear", "watch", "bull", "na"):
            r["status"] = "na"
        out.append({**base, **{k: v for k, v in r.items() if v is not None}})

    # change log
    changes = list((prev or {}).get("changes", []))
    if prev:
        for x in out:
            o = prev_by.get(x["id"])
            if o and o.get("status") != x["status"] and not x.get("stale"):
                changes.insert(0, dict(id=x["id"], name=x["name"], frm=o.get("status"), to=x["status"],
                                       reading=x.get("reading", ""), at=now.isoformat()))
    changes = changes[:40]

    charts = None
    try:
        charts = dict(margin=margin_charts())
    except Exception as e:
        log(f"charts failed: {e}")
        charts = (prev or {}).get("charts")

    counts = {k: sum(1 for x in out if x["status"] == k) for k in ("bear", "watch", "bull", "na")}
    payload = dict(
        site=CFG["site"]["name"],
        generated=now.isoformat(),
        counts=counts,
        failures=failures,
        indicators=out,
        changes=changes,
        charts=charts,
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    log(f"wrote {OUT.relative_to(ROOT)}: {counts}, {failures} source failures")
    # Fail the job only if nearly everything broke, so one flaky source never takes the site down.
    auto = sum(1 for i in CFG["indicators"] if i["mode"] == "auto")
    return 1 if failures >= auto else 0


if __name__ == "__main__":
    sys.exit(main())
