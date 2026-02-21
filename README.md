# Uber Ride Data Scraper

Scrapes detailed ride-by-ride earnings data from the Uber driver dashboard using Playwright. Outputs to `uber_rides.csv`.

## Why This Exists

Uber doesn't provide a bulk export of per-ride earnings breakdowns (distance pay, time pay, surge, fees, tips, etc.). This scraper navigates the driver dashboard week by week, clicks into each trip, and extracts the full fare breakdown.

## Requires Manual Interaction

This scraper **cannot run fully unattended**. Uber's dashboard triggers CAPTCHA/security challenges (photo puzzles, "one more step" checks) that must be completed manually in the browser. The scraper detects these and pauses, prompting you to complete the challenge and press Enter.

Because of this, **keep this project separate from the budget-management sync pipeline**. Run it manually when you need fresh ride data, then import the CSV into the budget DB.

## How to Run

```bash
# Install dependencies
pip install playwright
playwright install chromium

# Run the scraper
python uber_scraper_main.py
```

1. A Chromium browser opens to the Uber driver dashboard
2. Log in and complete any initial security checks
3. Enter a start date (any format: `Feb 9`, `2024-07-01`, `02/09/2024`, etc.)
   - The scraper snaps to the Monday of that week automatically
4. It scrapes each week's trips, advancing week by week
5. Complete CAPTCHA challenges when prompted
6. Stops when it reaches the current week or hits 3 consecutive empty weeks

## Output

`uber_rides.csv` with columns:

| Column | Example |
|--------|---------|
| Date | Feb 17, 2026 |
| Time | 4:45 AM |
| Ride Type | Electric / Premier |
| Distance Pay, Time Pay, Surge, Promotion, Base | Dollar amounts |
| Fare (subtotal), Tip | Dollar amounts |
| Minimum Fare Supplement, Wait Time Pay | Dollar amounts |
| Region/City Fee, Airport Fee | Dollar amounts |
| Insurance & Operational Fee, Uber Service Fee | Dollar amounts |
| Points Earned | Integer |
| City | City name |
| Pickup Address, Dropoff Address | Full address |
| Distance (mi), Duration (min) | Numeric |
| $/mile, $/min | Rate per unit |
| Total Earnings, Total Customer Fare | Dollar amounts |

## Integration with Budget Management

This CSV feeds into the budget-management project's rideshare pipeline:

```
uber_scraper_main.py → uber_rides.csv → budget-management import → raw.rideshare_rides → analytics
```

**After scraping**, import into the budget DB:
```bash
cd ~/Projects/budget-management
python scripts/rideshare/import_rideshare_rides.py
```

Or run the full sync pipeline which includes rideshare import + forecast regeneration:
```bash
python scripts/sync.py
```

The import script handles deduplication, so re-importing overlapping date ranges is safe.

## Files

| File | Purpose |
|------|---------|
| `uber_scraper_main.py` | Main scraper — use this one |
| `uber_scraper_weekloop_test.py` | Test script for week navigation only (no scraping) |
| `uber_scraper_merged.py` | Earlier version (archived) |
| `uber_scraper_weekloop_*.py` | Earlier weekloop attempts (archived) |
| `webscrape_UberDetails.ipynb` | Original Jupyter notebook prototype |
| `browser_profile/` | Chromium profile (persists login session) |

## Week Navigation

The scraper types date ranges directly into the "Search by week" input field on the Uber dashboard (e.g., `Feb 9, 2026 – Feb 16, 2026`). This replaced an earlier approach that tried to click calendar picker elements, which was unreliable.

## Notes

- `browser_profile/` persists your Uber login between runs so you don't re-authenticate every time
- The CSV appends — it won't overwrite existing data. To start fresh, delete `uber_rides.csv`
- Security challenges seem to trigger more frequently with rapid navigation. The random delays help but don't eliminate them
