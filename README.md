# CalorieBase

A static "calories in [food]" site generated from the USDA FoodData Central
SR Legacy database (public domain). Every food page is built from real USDA
nutrition data, giving each page genuinely unique, useful content.

## Why this approach

Mass-generated AI articles are penalized by Google in 2026. Data-driven pages
built from a real authoritative dataset (USDA) are exactly the pattern Google
still rewards: comparison/table content, real structured data, unique per-page
values. The site ships static HTML on a fast CDN (Cloudflare Pages) with
sitemap, canonical URLs, breadcrumbs, and Schema.org structured data.

## How it works

- `data/sr/` — raw USDA SR Legacy ASCII files (downloaded from data.gov mirror)
- `src/generate.py` — the generator (Python 3, stdlib only)
- `out/` — the generated static site (what gets deployed)

## Build

```
python src/generate.py --curated   # launch set (~380 most-searched foods)
python src/generate.py             # full build (all ~7,700 foods)
python src/generate.py --top 500   # next 500 most-ranked foods
```

## Deploy

Static site — host `out/` anywhere. Recommended: Cloudflare Pages (free).
Point the build output at the `out` directory, or push the repo to GitHub and
connect it in the Cloudflare dashboard.

Data source: U.S. Department of Agriculture, Agricultural Research Service.
FoodData Central, SR Legacy. Public domain.
