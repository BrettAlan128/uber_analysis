"""Uber Ride Data Scraper — Merged Version

Combines:
- Current version: sync Playwright, persistent profile, detailed trip extraction,
  security challenge handling, Load More, resume from CSV
- Old version (Jan 2026): simple working week loop using "Previous" button

This version scrapes BACKWARDS from the current week (or wherever you start)
using the "Previous" button to move through weeks, instead of the broken
calendar-based forward navigation.
"""

import csv
import os
import random
import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

START_DATE = "2024-07-01"
OUTPUT_FILE = "uber_rides.csv"
BROWSER_PROFILE_DIR = "browser_profile"

HEADERS = [
    "Date", "Time", "Ride Type", "Distance Pay", "Time Pay", "Surge", "Promotion",
    "Base", "Fare (subtotal)", "Tip", "Minimum Fare Supplement", "Wait Time Pay",
    "Region/City Fee", "Airport Fee", "Insurance & Operational Fee", "Uber Service Fee",
    "Points Earned", "City", "Pickup Address", "Dropoff Address", "Distance (mi)",
    "Duration (min)", "$/mile", "$/min", "Total Earnings", "Total Customer Fare"
]


def random_delay(min_sec=1, max_sec=3):
    time.sleep(random.uniform(min_sec, max_sec))


def extract_trip_data(page) -> dict:
    return page.evaluate(r"""
    () => {
        const headerText = document.querySelector('[class*="trip"] span, [class*="list"] span')?.textContent || '';
        const headerMatch = headerText.match(/(.+?)\s*•\s*(.+?)\s*•\s*(.+)/);
        const rideType = headerMatch ? headerMatch[1].trim() : '';
        const date = headerMatch ? headerMatch[2].trim() : '';
        const time = headerMatch ? headerMatch[3].trim() : '';

        const durationEl = [...document.querySelectorAll('*')].find(el =>
            el.textContent.includes('min') && el.textContent.includes('sec') && el.children.length === 0);
        const duration = durationEl ? durationEl.textContent.trim() : '';

        const distanceEl = [...document.querySelectorAll('*')].find(el =>
            el.textContent.match(/^\d+\.\d+\s*mi$/) && el.children.length === 0);
        const distance = distanceEl ? distanceEl.textContent.replace(' mi', '').trim() : '';

        const addresses = [...document.querySelectorAll('*')]
            .filter(el => el.textContent.includes(', US') && el.children.length === 0)
            .map(el => el.textContent.trim())
            .filter((v, i, a) => a.indexOf(v) === i);
        const pickup = addresses[0] || '';
        const dropoff = addresses[1] || '';

        const cityMatch = pickup.match(/,\s*([^,]+),\s*[A-Z]{2},\s*US/);
        const city = cityMatch ? cityMatch[1].trim() : '';

        const pointsEl = [...document.querySelectorAll('*')].find(el =>
            el.textContent.match(/^\d+\s*points?\s*earned$/) && el.children.length === 0);
        const points = pointsEl ? pointsEl.textContent.match(/(\d+)/)[1] : '0';

        let base = '0', distancePay = '0', timePay = '0', surge = '0', promotion = '0';
        let tip = '0', minFare = '0', waitTime = '0', fare = '0', totalEarnings = '0';
        let regionFee = '0', airportFee = '0', insuranceFee = '0', uberFee = '0', customerFare = '0';
        let perMile = '0', perMin = '0';

        const allText = document.body.innerText;
        const mileMatch = allText.match(/\$(\d+\.\d+)\/mile/);
        const minMatch = allText.match(/\$(\d+\.\d+)\/min/);
        perMile = mileMatch ? mileMatch[1] : '0';
        perMin = minMatch ? minMatch[1] : '0';

        const items = [...document.querySelectorAll('li')];
        items.forEach(item => {
            const text = item.textContent;
            const valueMatch = text.match(/\$(\d+\.?\d*)/);
            const value = valueMatch ? valueMatch[1] : '0';
            if (text.includes('Base') && !text.includes('Fare')) base = value;
            if (text.includes('Distance') && text.includes('mile')) distancePay = value;
            if (text.includes('Time') && text.includes('minute')) timePay = value;
            if (text.includes('Surge')) surge = value;
            if (text.includes('Promotion')) promotion = value;
            if (text.includes('Minimum Fare')) minFare = value;
            if (text.includes('Wait Time')) waitTime = value;
            if (text.match(/^Fare\s*\$/) || (text.includes('Fare') && !text.includes('customer') && !text.includes('Minimum'))) {
                if (text.match(/Fare\s*\$(\d+\.?\d*)/)) fare = text.match(/Fare\s*\$(\d+\.?\d*)/)[1];
            }
            if (text.includes('Your earnings') && !text.includes('Total')) totalEarnings = value;
            if (text.includes('Tip') && !text.includes('included')) tip = value;
        });

        const regionMatch = allText.match(/Region or City Fee[^-]*-\$(\d+\.?\d*)/);
        const airportMatch = allText.match(/Airport Fee[^-]*-\$(\d+\.?\d*)/);
        const insuranceMatch = allText.match(/insurance and operational[^-]*-\$(\d+\.?\d*)/i);
        const uberMatch = allText.match(/Uber Service Fee[^$]*\$(\d+\.?\d*)/);
        const customerMatch = allText.match(/Total customer fare[^$]*\$(\d+\.?\d*)/);
        regionFee = regionMatch ? regionMatch[1] : '0';
        airportFee = airportMatch ? airportMatch[1] : '0';
        insuranceFee = insuranceMatch ? insuranceMatch[1] : '0';
        uberFee = uberMatch ? uberMatch[1] : '0';
        customerFare = customerMatch ? customerMatch[1] : '0';

        const totalEl = document.querySelector('h1, h2, [class*="heading"]');
        if (totalEl && totalEl.textContent.includes('$')) {
            const match = totalEl.textContent.match(/\$(\d+\.?\d*)/);
            if (match) totalEarnings = match[1];
        }
        if (tip === '0') {
            const tipMatch = allText.match(/\$(\d+\.?\d*)\s*tip included/);
            if (tipMatch) tip = tipMatch[1];
        }
        const durMatch = duration.match(/(\d+)\s*min\s*(\d+)\s*sec/);
        const durationMin = durMatch ? (parseInt(durMatch[1]) + parseInt(durMatch[2])/60).toFixed(2) : '0';

        return { date, time, rideType, distancePay, timePay, surge, promotion, base, fare, tip,
            minFare, waitTime, regionFee, airportFee, insuranceFee, uberFee, points, city,
            pickup, dropoff, distance, durationMin, perMile, perMin, totalEarnings, customerFare };
    }
    """)


def check_for_security_challenge(page) -> bool:
    try:
        page_text = page.inner_text("body", timeout=2000)
        if "security check" in page_text.lower() or "one more step" in page_text.lower():
            return True
    except:
        pass
    return False


def wait_for_security_clear(page):
    print("")
    print("  SECURITY CHECK DETECTED!")
    print("  Complete the check in browser, then press Enter...")
    input()
    random_delay(2, 4)


def click_load_more(page):
    """Click Load More button until no more trips — from current version."""
    selectors = ["button:has-text('Load more')", "button:has-text('Load More')"]
    count = 0
    while True:
        if check_for_security_challenge(page):
            wait_for_security_clear(page)
        found = False
        for sel in selectors:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=2000):
                    random_delay(0.5, 1.5)
                    btn.click()
                    count += 1
                    print(f"    Load More clicked {count}x", end="\r")
                    random_delay(2, 4)
                    found = True
                    break
            except:
                pass
        if not found:
            break
    if count > 0:
        print(f"    Clicked Load More {count} times          ")


def get_trip_urls(page) -> list:
    """Get all trip detail URLs on the current page — from current version."""
    return page.evaluate("""() => {
        return [...document.querySelectorAll('a[href*="/earnings/trips/"]')]
            .map(a => a.href).filter((v,i,a) => a.indexOf(v) === i);
    }""")


def get_week_display(page) -> str:
    """Get the current week's date range text — from current version."""
    try:
        el = page.locator("text=/[A-Z][a-z]{2} \\d+.*–.*\\d{4}/").first
        return el.inner_text(timeout=3000)
    except:
        return "Unknown"


def click_previous_week(page) -> bool:
    """Click the Previous week button — from old working version.

    This is the simple, proven approach that replaces the broken
    calendar-based navigation.
    """
    selectors = [
        "button:has-text('Previous')",
        "button:has-text('Prev')",
        "button[aria-label*='Previous']",
        "button[aria-label*='previous']",
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                btn.click()
                page.wait_for_load_state("networkidle")
                random_delay(1, 2)
                return True
        except:
            continue
    return False


def save_csv(trips, path):
    """Save trips to CSV, appending if file exists — from current version."""
    if not trips:
        return
    exists = os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(HEADERS)
        for t in trips:
            w.writerow([t["date"], t["time"], t["rideType"], t["distancePay"], t["timePay"],
                t["surge"], t["promotion"], t["base"], t["fare"], t["tip"], t["minFare"],
                t["waitTime"], t["regionFee"], t["airportFee"], t["insuranceFee"], t["uberFee"],
                t["points"], t["city"], t["pickup"], t["dropoff"], t["distance"], t["durationMin"],
                t["perMile"], t["perMin"], t["totalEarnings"], t["customerFare"]])


def get_last_date(path):
    """Check existing CSV for last scraped date — from current version."""
    if not os.path.exists(path):
        return None, 0
    try:
        with open(path) as f:
            reader = csv.DictReader(f)
            dates, count = [], 0
            for row in reader:
                count += 1
                if row.get("Date"):
                    try:
                        dates.append(datetime.strptime(row["Date"], "%b %d, %Y"))
                    except:
                        pass
            if dates:
                return max(dates).strftime("%b %d, %Y"), count
            return None, count
    except:
        return None, 0


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output = os.path.join(script_dir, OUTPUT_FILE)
    profile = os.path.join(script_dir, BROWSER_PROFILE_DIR)

    print("")
    print(f"Output: {output}")
    print(f"Profile: {profile}")

    last, rows = get_last_date(output)
    if last:
        print(f"Found {rows} existing trips. Last: {last}")
    else:
        print(f"No dates found. {rows} rows in CSV.")

    total = rows

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(profile, headless=False,
            viewport={"width": 1280, "height": 900}, slow_mo=50)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://drivers.uber.com/earnings/activities")

        print("")
        print("=" * 50)
        print("Log in, complete security, navigate to the week")
        print("you want to START scraping from.")
        print("The scraper will go BACKWARDS from there using")
        print("the Previous button.")
        print("=" * 50)
        input("Press Enter when ready...")

        week_num = 0
        empty_streak = 0

        # --- Week loop: from old working version ---
        # Simple approach: scrape current week, click Previous, repeat
        while True:
            week_num += 1
            week_text = get_week_display(page)
            print(f"\n--- Week {week_num}: {week_text} ---")

            try:
                # Check for security challenges (from current version)
                if check_for_security_challenge(page):
                    wait_for_security_clear(page)
                    page.goto("https://drivers.uber.com/earnings/activities")
                    page.wait_for_load_state("networkidle")
                    random_delay(2, 3)

                # Load all trips for this week (from current version)
                print("  Loading rides...")
                click_load_more(page)

                # Get trip URLs (from current version)
                urls = get_trip_urls(page)
                print(f"  Found {len(urls)} trips")

                if not urls:
                    empty_streak += 1
                    if empty_streak >= 3:
                        print("3 empty weeks in a row. Done.")
                        break
                else:
                    empty_streak = 0

                # Scrape each trip (from current version — detailed extraction)
                trips = []
                for i, url in enumerate(urls, 1):
                    print(f"  Scraping {i}/{len(urls)}...", end="\r")
                    try:
                        if check_for_security_challenge(page):
                            wait_for_security_clear(page)
                        page.goto(url)
                        page.wait_for_load_state("networkidle")
                        random_delay(0.5, 1.5)
                        # Try to expand fare breakdown
                        try:
                            btn = page.locator("text=View fare breakdown").first
                            if btn.is_visible(timeout=1000):
                                btn.click()
                                random_delay(0.3, 0.7)
                        except:
                            pass
                        trips.append(extract_trip_data(page))
                    except Exception as e:
                        print(f"  Error trip {i}: {e}")

                if trips:
                    print(f"  Scraped {len(trips)} trips          ")
                    save_csv(trips, output)
                    total += len(trips)
                    print(f"  Saved. Total: {total}")

                # Navigate back to activities page before clicking Previous
                page.goto("https://drivers.uber.com/earnings/activities")
                page.wait_for_load_state("networkidle")
                random_delay(1, 2)

                # --- Click Previous to go to prior week (from old version) ---
                print("  Going to previous week...")
                if not click_previous_week(page):
                    print("  Could not find Previous button.")
                    resp = input("  Navigate manually, Enter to continue or 'stop': ")
                    if resp.lower() == 'stop':
                        break

            except Exception as e:
                print(f"Error: {e}")
                resp = input("Enter to retry, 'skip', or 'stop': ")
                if resp == 'stop':
                    break
                elif resp == 'skip':
                    # Try to go to previous week anyway
                    page.goto("https://drivers.uber.com/earnings/activities")
                    page.wait_for_load_state("networkidle")
                    click_previous_week(page)
                else:
                    week_num -= 1

        print("")
        print("=" * 50)
        print(f"DONE! Total: {total}")
        print(f"Saved: {output}")
        print("=" * 50)
        ctx.close()


if __name__ == "__main__":
    main()
