# Analytica Horizon Technology — website and live data

The public website for **analyticahorizon.com**, with live macroeconomic and commodity-futures data.

| Page | Path | What's on it |
|---|---|---|
| Home | `/` | Macro Pulse ring, live indicator tiles, regime read, energy and positioning snapshot |
| Macro Monitor | `/monitor/` | All 56 indicators, status-change log, margin debt since 1997 |
| Commodities | `/commodities/` | EIA energy prices, CFTC managed-money positioning for 8 futures markets |
| Solutions | `/solutions/` | Platform, research, data/API, institutional engagements |
| Technology | `/technology/` | Pipeline, scoring, machine learning, data provenance |
| Research | `/research/` | Latest outlook note |
| About | `/about/` | Company, principles, ADGM details |
| Contact | `/contact/` | Demo and enquiry form (Formspree) |
| Legal | `/legal/` | Disclaimer, terms, privacy notice, data sources |

**Editing pages:** the page text lives in `tools/pages/*.html`, and shared settings (company name, ADGM registration number, registered office, Formspree form ID) in `tools/site.json`. After editing, run `python tools/build_site.py` to regenerate `site/`. You can also edit the generated files in `site/` directly on GitHub for small text fixes, but those changes are overwritten the next time the build script runs.

**Contact form (Formspree):**
1. Create a free account at https://formspree.io and add a new form. Set its email to the inbox that should receive enquiries.
2. Copy the form ID: the part after `/f/` in the endpoint, for example `xyzabcd`.
3. Put it in `tools/site.json` as `"formspree_id": "xyzabcd"` and run the build script, or edit `site/contact/index.html` and set `data-formspree="xyzabcd"` on the form.
Until the ID is set, the form shows "being connected" and its send button is disabled.

**Company details in the footer:** add your ADGM registration number and registered office address to `tools/site.json`. They appear in every page footer once filled in.

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

### 5. Point analyticahorizon.com at it (GoDaddy)
1. In GitHub, go to **Settings → Pages → Custom domain**, enter `analyticahorizon.com`, and click **Save**.
2. Recommended first: in your GitHub **account** (not repo) **Settings → Pages → Add a domain**, enter `analyticahorizon.com`. GitHub shows a TXT record for verifying the domain; add it in step 4.
3. In GoDaddy, go to **My Products → Domains → analyticahorizon.com → DNS** (sometimes labeled **Manage DNS**).
   - If **Forwarding** is turned on for the domain, remove it.
   - If the domain is connected to GoDaddy Website Builder or a parked page, disconnect it. Otherwise GoDaddy keeps overriding the records.
4. In the **DNS Records** table:

   | Action | Type | Name | Value | TTL |
   |---|---|---|---|---|
   | Delete or edit the existing one | A | @ | (usually "Parked" or a GoDaddy IP) | |
   | Add | A | @ | 185.199.108.153 | 1 hour |
   | Add | A | @ | 185.199.109.153 | 1 hour |
   | Add | A | @ | 185.199.110.153 | 1 hour |
   | Add | A | @ | 185.199.111.153 | 1 hour |
   | Edit the existing one | CNAME | www | `<your-github-username>.github.io` | 1 hour |
   | Add (from step 2) | TXT | `_github-pages-challenge-<username>` | the code GitHub gave you | 1 hour |

   Leave the NS and SOA records alone, and leave any MX records alone if you use email on this domain.
5. Wait for DNS to update (usually 10–60 minutes; up to 24 hours). When GitHub's Pages settings show "DNS check successful", tick **Enforce HTTPS**. The certificate can take up to an hour to appear.

On another registrar, the records are the same: four A records on `@` and a `www` CNAME to `<your-github-username>.github.io`.

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
