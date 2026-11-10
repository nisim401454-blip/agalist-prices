# agalist-prices

Nightly public supermarket price data for the **עגליסט** shopping-list app.

Israeli supermarket chains publish their full price lists every day under the price-transparency
regulations. This repository downloads those public files once a night, shrinks them, and publishes
small JSON files that the app reads directly from GitHub Pages. No server, no keys, no personal data.

## How it works

1. `fetch_chain.py <CHAIN>` runs once per chain (GitHub Actions matrix). It downloads the chain's store
   list and full price files with [il-supermarket-scraper](https://github.com/OpenIsraeliSupermarkets/israeli-supermarket-scarpers)
   and writes a compact file: a base price list per sub-chain plus per-store differences.
2. `build.py` merges the chains, keeps the products sold by at least two chains (matched by barcode),
   matches loose produce and meat by name (`generics.json`), locates stores on the map
   (OpenStreetMap Nominatim, cached in `geo.json`), and writes the published files.
3. The result is deployed to GitHub Pages. If a chain fails on a given night, the last published
   file for that chain is reused.

## Published files (`https://nisim401454-blip.github.io/agalist-prices/`)

| File | Content |
|---|---|
| `products.json` | product list: code, name, maker, size, number of stores and chains |
| `cities.json` | cities that have stores, with a center point and store count |
| `city/<code>.json` | the stores of one city, their location and prices |
| `chains.json` | chain display names and data date |
| `status.json` | what happened in the last run (also committed to `status/status.json`) |

## Settings (`config.json`)

- `chains`: chains to download. Chains that block access from outside Israel are not listed.
- `max_products`, `min_chains`: size of the product list.
- `geocode_budget`: maximum map lookups per night (new stores only; results are cached).

The schedule is in `.github/workflows/`. Times are UTC.
