# Analytica Horizon — Market Signal Board

A public, self-updating dashboard for **analyticahorizon.com** that tracks 56 indicators of S&P 500 correction risk vs. support for further gains.

- **20 live indicators** refresh automatically from public sources: Federal Reserve / FRED, US Treasury, BLS, EIA, DOL, CFTC and FINRA.
- **36 analyst indicators** come from `config/manual.json`, which you edit by hand. Rows whose data comes from licensed providers show only your status and commentary, never the provider's numbers.
- **Margin debt history** since 1997 (FINRA), shown four ways: balance, year-over-year change, % of GDP, and cash cushion.
- **Status changes are logged automatically** and shown in the "What changed" panel.
- The page re-checks for new data every 5 minutes while it's open.

It's a static site (no server, no database), hosted free on GitHub Pages. A GitHub Actions job rebuilds the data every 30 minutes during US market hours, plus once nightly.

```
config/indicators.json   indicator definitions, sources, thresholds, licensing flag
config/manual.json       analyst readings you maintain
scripts/update.py        fetches data, scores indicators, writes site/data/indicators.json
site/                    the website (index.html, assets/, data/)
.github/workflows/       the scheduled update-and-deploy job
tests/                   offline test fixtures (synthetic; never publish a build made from them)
```

---

## One-time setup (about 20 minutes)

### 1. Put the code on GitHub
1. Sign in at github.com, or create a free account.
2. Create a new **public** repository, for example `signal-board`. (GitHub Pages on a private repo needs a paid plan.)
3. Upload every file and folder in this package, including the hidden `.github` folder. You can drag them onto the repo's "Add file → Upload files" page, or use `git push`.

### 2. Add a free FRED API key
1. Request a key at https://fred.stlouisfed.org/docs/api/api_key.html (instant, free).
2. In the repo, go to **Settings → Secrets and variables → Actions → New repository secret**.
3. Name it `FRED_API_KEY` and paste the key as the value.

### 3. Turn on GitHub Pages
1. Go to **Settings → Pages**.
2. Under **Build and deployment → Source**, choose **GitHub Actions**.

### 4. Run the first build
1. Go to the **Actions** tab. If asked, enable workflows.
2. Open **Update data and deploy**, click **Run workflow**, and wait about 2 minutes.
3. The site is now live at `https://<your-username>.github.io/<repo>/`. Check it there before switching the domain over.

### 5. Point analyticahorizon.com at it
1. In **Settings → Pages → Custom domain**, enter `analyticahorizon.com` and save.
2. At your domain registrar's DNS settings, add these records:

   | Type | Host / Name | Value |
   |---|---|---|
   | A | @ | 185.199.108.153 |
   | A | @ | 185.199.109.153 |
   | A | @ | 185.199.110.153 |
   | A | @ | 185.199.111.153 |
   | CNAME | www | `<your-username>.github.io` |

   Remove any other A or AAAA records on `@` (for example, a registrar "parked" page).
3. DNS changes can take anywhere from a few minutes to 24 hours. Once GitHub shows the domain as verified, tick **Enforce HTTPS**.
4. Recommended: verify the domain under your GitHub **account** settings (**Settings → Pages → Add a domain**). This stops anyone else from claiming it.

---

## Keeping it current

**Live indicators** update themselves. How often the numbers actually change depends on the source:

| Updates | Series |
|---|---|
| Daily (evening) | 10-yr and real yields, curve, term premium, fed funds, dollar, oil |
| Weekly | Jobless claims, Fed balance sheet, Chicago Fed NFCI, CFTC positioning (Fridays) |
| Monthly | CPI, Sahm rule, FINRA margin debt (around the 3rd week) |
| Quarterly | Bank lending survey, loan delinquency, money fund assets, GDP |
| Per auction | Treasury auction demand |

The 30-minute schedule picks up each release soon after it's published. Free public sources don't offer intraday values. True intraday data (live yields, VIX, S&P level) needs a paid, licensed feed.

**Analyst indicators:** edit `config/manual.json` directly on GitHub (open the file, click the pencil icon, then **Commit**). The site redeploys within about 2 minutes. Each entry looks like this (the `//` comments are explanations only; leave them out of the real file):

```json
"vix": {
  "reading": "14.2",           // shown only if the indicator is public, or if show_restricted_values is true
  "status": "watch",           // bear | watch | bull | na
  "asOf": "2026-09-22",
  "note": "Private working note",
  "public_note": "Implied volatility is low, a sign of calm or complacency."   // shown on the site for licensed rows
}
```

**Thresholds** for live indicators are in `config/indicators.json` (`bear` / `watch` values) and in the matching `calc_*` function in `scripts/update.py`.

**If a source is down,** the site keeps its last good value, marks the row **Delayed**, and keeps running. The job fails only if every live source fails at once.

**Why the nightly run commits a snapshot:** GitHub pauses scheduled workflows on repos with no activity for 60 days. The nightly commit keeps the schedule running.

---

## Before you publicize the site: licensing and compliance

- **Licensed data is hidden by default.** S&P 500 levels and ratios, ICE BofA credit spreads, Cboe VIX and put/call, FactSet earnings data, AAII sentiment and similar sources don't allow public republication without permission. Those rows show only your assessment. `show_restricted_values` in `config/indicators.json` stays `false` unless you have licenses that allow display.
- **Public-domain sources** (Federal Reserve Board, Treasury, BLS, EIA, DOL, CFTC) are shown with attribution. The Chicago Fed (NFCI) and FINRA figures are shown with attribution too; check each publisher's terms if you plan commercial use.
- **Regulatory review:** if you or your firm are registered with the CFTC or NFA, public market commentary and "bullish/bearish" signals may count as communications with the public under NFA rules. Have your compliance contact review the page, and add any disclosure they require, before promoting it. The footer disclaimer in `site/index.html` is a starting point, not a substitute for that review.

---

## Testing locally (optional)

```bash
pip install -r requirements.txt
python tests/make_fixtures.py                       # synthetic sample data
AH_FIXTURES=tests/fixtures AH_PREVIOUS=none python scripts/update.py
python -m http.server 8000 -d site                  # open http://localhost:8000
```

Delete `site/data/indicators.json` afterwards so a synthetic build is never published. The workflow always rebuilds it from live sources anyway.
