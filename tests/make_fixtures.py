"""Generate SYNTHETIC fixtures for offline testing of scripts/update.py.

Histories are random walks ending near recently observed values. They are
test data only: never publish a build made from these fixtures.
"""
import json, random
from datetime import date, timedelta
from pathlib import Path

random.seed(7)
OUT = Path(__file__).parent / "fixtures"
OUT.mkdir(exist_ok=True)
END = date(2026, 9, 23)

def walk(end_value, n, step, freq_days, floor=None):
    vals = [end_value]
    for _ in range(n - 1):
        v = vals[-1] - random.gauss(0, step)
        vals.append(max(floor, v) if floor is not None else v)
    vals.reverse()
    return [((END - timedelta(days=freq_days * (n - 1 - i))).isoformat(), round(v, 4)) for i, v in enumerate(vals)]

def monthly(end_value, n, growth):
    out = []
    v = end_value
    for i in range(n):
        m = 8 - i
        y = 2026 + (m - 1) // 12
        mm = (m - 1) % 12 + 1
        out.append((date(y, mm, 1).isoformat(), round(v, 3)))
        v = v / (1 + growth / 12)
    return out[::-1]

def fred(series, obs):
    (OUT / f"fred_{series}.json").write_text(json.dumps({"observations": [{"date": d, "value": str(v)} for d, v in obs]}))

fred("DGS10", walk(5.18, 800, 0.04, 1))
fred("DFII10", walk(2.63, 800, 0.03, 1))
fred("THREEFYTP10", walk(0.96, 800, 0.02, 1))
fred("DFF", walk(3.88, 800, 0.01, 1))
fred("WALCL", walk(6746548, 160, 8000, 7))
fred("T10Y2Y", walk(0.26, 800, 0.03, 1))
fred("DTWEXBGS", walk(119.5, 800, 0.3, 1))
fred("DRTSCILM", walk(0.0, 16, 4, 91))
fred("NFCI", walk(-0.555, 160, 0.02, 7))
fred("DRBLACBS", walk(1.27, 18, 0.03, 91))
fred("SAHMREALTIME", walk(-0.07, 40, 0.05, 30))
fred("ICSA", walk(197000, 160, 6000, 7, floor=150000))
fred("DCOILWTICO", walk(96.41, 800, 1.2, 1, floor=40))
fred("CPILFESL", monthly(337.765, 50, 0.024))
fred("CPIAUCSL", monthly(330.0, 50, 0.034))
fred("MMMFFAQ027S", [("2025-04-01", "7481232"), ("2025-07-01", "7774054"), ("2025-10-01", "8190235"), ("2026-01-01", "8289569"), ("2026-04-01", "8441374")])
fred("GDP", [(date(y, m, 1).isoformat(), round(20000 * (1.045 ** (y - 2020 + (m - 1) / 12)), 1)) for y in range(1996, 2027) for m in (1, 4, 7, 10)])

# FINRA: debit balances as published (Jun 2022 - Aug 2026, $ millions); free credits only where available
debits = [683440,696780,687790,664010,649620,643780,606660,641230,624380,645430,631950,644170,681230,709830,689180,680850,635280,660890,700770,701980,742960,784140,775460,809430,809320,810840,797160,813210,815370,890850,899170,937250,918140,880320,850560,920960,1008000,1023000,1059723,1126494,1183654,1214321,1225597,1279042,1253192,1220922,1304281,1415557,1502072,1417225,1453832]
cash = {"2025-08":(188221,181563),"2025-09":(204106,194884),"2025-10":(197923,195376),"2025-11":(202131,194418),"2025-12":(211720,199762),"2026-01":(203700,196911),"2026-02":(205060,200047),"2026-03":(221860,205600),"2026-04":(217836,215445),"2026-05":(206600,217256),"2026-06":(217441,223412),"2026-07":(205132,217305),"2026-08":(207641,217499)}
rows = []
y, m = 2022, 6
for d in debits:
    k = f"{y}-{m:02d}"
    c = cash.get(k)
    rows.append({"date": f"{k}-01", "debit": d, "cash_free": c[0] if c else None, "margin_free": c[1] if c else None})
    m += 1
    if m > 12: m, y = 1, y + 1
(OUT / "finra.json").write_text(json.dumps(rows))

(OUT / "auctions.json").write_text(json.dumps([
 {"auction_date":"2026-09-17","security_term":"9-Year 10-Month","security_type":"Note","high_yield":"2.653","bid_to_cover_ratio":"2.24","inflation_index_security":"Yes"},
 {"auction_date":"2026-09-09","security_term":"9-Year 11-Month","security_type":"Note","high_yield":"4.834","bid_to_cover_ratio":"2.71","inflation_index_security":"No"},
 {"auction_date":"2026-09-10","security_term":"29-Year 11-Month","security_type":"Bond","high_yield":"5.310","bid_to_cover_ratio":"2.61","inflation_index_security":"No"}]))

cftc = []
for i in range(160):
    d = END - timedelta(days=7 * i + 8)
    am_long = 1142075 + random.randint(-150000, 50000) if i else 1142075
    cftc.append({"report_date_as_yyyy_mm_dd": d.isoformat() + "T00:00:00.000", "open_interest_all": "2446519",
                 "asset_mgr_positions_long": str(am_long), "asset_mgr_positions_short": "237391",
                 "lev_money_positions_long": "161176", "lev_money_positions_short": "454319"})
(OUT / "cftc.json").write_text(json.dumps(cftc))
print("fixtures written")
