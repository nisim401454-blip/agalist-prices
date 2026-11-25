# agalist-prices

Weekly public supermarket price data for the **עגליסט** shopping-list app.

Israeli supermarket chains publish their full price lists every day under the price-transparency
regulations. This repository downloads those public files once a week (Sunday, Israel time), shrinks them, and publishes
small JSON files that the app reads directly from GitHub Pages. No server, no keys, no personal data.

## How it works

1. `plan.py` decides whether to run: it skips when another price run is already active, and a backup
   Sunday attempt skips itself once that Sunday's prices are live.
2. `fetch_chain.py <CHAIN>` runs once per chain (GitHub Actions matrix). It downloads the chain's store
   list and full price files with [il-supermarket-scraper](https://github.com/OpenIsraeliSupermarkets/israeli-supermarket-scarpers)
   and writes a compact file: a base price list per sub-chain plus per-store differences.
3. `build.py` merges the chains, keeps the products sold by at least two chains (matched by barcode),
   matches loose produce and meat by name (`generics.json`), locates stores on the map
   (OpenStreetMap Nominatim, cached in `geo.json`), and writes the site. If a chain fails, the last
   published file for that chain is reused and marked as older. The built site is kept for 14 days
   as the `site` artifact of the run.
4. `publish.yml` puts a built site on GitHub Pages (`stamp.py` adds the publication time first).
   Only a publication that went live updates `status/status.json`. If publishing fails, Pages keeps
   the last version that worked, and the publish can be retried on its own from the built site.
5. `health.py` opens a GitHub issue when the weekly update did not go live, and a separate one when
   the live prices include a chain with older files. `watch.yml` checks on Monday morning that the
   week's prices were published at all.

## Schedule and manual runs

| What | When / how |
|---|---|
| Weekly update | Sunday 12:47 UTC (14:47 Israel in winter, 15:47 in summer), after the last chain publishes |
| Backup attempts | Sunday 14:47 and 16:47 UTC; they skip themselves when Sunday's prices are already live |
| Monday check | Monday 05:17 UTC (`weekly watch`) |
| Refresh now | Actions > **weekly prices** > Run workflow. Does nothing if a price run is already active |
| Retry only the publish | Actions > **publish prices** > Run workflow (run number, or empty for the newest built site) |

A click on Run workflow only starts a run. The prices are updated when `updated.json` shows the new time.

## Published files (`https://nisim401454-blip.github.io/agalist-prices/`)

| File | Content |
|---|---|
| `products.json` | product list: code, name, maker, size, number of stores and chains |
| `cities.json` | cities that have stores, with a center point and store count |
| `city/<code>.json` | the stores of one city, their location and prices |
| `chains.json` | chain display names and data date |
| `updated.json` | when the live prices were published, their date, and chains that rely on older files |
| `status.json` | details of the published run (also committed to `status/status.json`) |

## Settings (`config.json`)

- `chains`: chains to download. Chains that block access from outside Israel are not listed.
- `max_products`, `min_chains`: size of the product list.
- `geocode_budget`: maximum map lookups per run (new stores only; results are cached).

The schedule is in `.github/workflows/`. Times are UTC.
