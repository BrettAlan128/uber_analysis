"""Uber Ride Data Scraper"""

import csv
import os
import random
import re
import time
from datetime import datetime, timedelta
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
    return page.evaluate("""() => {
        return [...document.querySelectorAll('a[href*="/earnings/trips/"]')]
            .map(a => a.href).filter((v,i,a) => a.indexOf(v) === i);
    }""")


def get_monday(d):
    """Return the Monday of the week containing date d."""
    return d - timedelta(days=d.weekday())


def format_week_range(monday):
    """Format a Monday date as 'Mon DD, YYYY \u2013 Mon DD, YYYY' (Monday to next Monday)."""
    end = monday + timedelta(days=7)
    return f"{monday.strftime('%b')} {monday.day}, {monday.year} \u2013 {end.strftime('%b')} {end.day}, {end.year}"


def navigate_to_week(page, monday):
    """Type a week range into the 'Search by week' input field."""
    week_str = format_week_range(monday)
    print(f"    Navigating to: {week_str}")
    # Find the search-by-week input
    search_input = page.locator("input").first
    search_input.click()
    random_delay(0.3, 0.5)
    # Triple-click to select all text, then type over it
    search_input.click(click_count=3)
    random_delay(0.2, 0.4)
    search_input.fill(week_str)
    random_delay(0.3, 0.5)
    search_input.press("Tab")
    page.wait_for_load_state("networkidle")
    random_delay(1, 2)


def save_csv(trips, path):
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
        print("Log in and complete any security checks.")
        print("=" * 50)
        inp = input("Enter start date (e.g. Jul 1, 2024) or Enter for today: ")
        if inp:
            inp = inp.strip()
            parsed = None
            for fmt in ["%b %d, %Y", "%b %d %Y", "%b %d", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y"]:
                try:
                    parsed = datetime.strptime(inp, fmt)
                    # If no year in format, assume current year
                    if "%Y" not in fmt and "%y" not in fmt:
                        parsed = parsed.replace(year=datetime.now().year)
                    break
                except:
                    continue
            if parsed:
                week_date = parsed
            else:
                print(f"Could not parse '{inp}', using today.")
                week_date = datetime.now()
        else:
            week_date = datetime.now()

        # Snap to Monday of that week
        week_date = get_monday(week_date)
        print(f"Starting from Monday: {week_date.strftime('%b %d, %Y')}")

        # Navigate to the first week
        navigate_to_week(page, week_date)

        week_num = 0
        empty = 0

        while True:
            week_num += 1
            print(f"\n--- Week {week_num}: {format_week_range(week_date)} ---")

            if week_date > datetime.now():
                print("Reached future week. Done.")
                break

            try:
                if check_for_security_challenge(page):
                    wait_for_security_clear(page)
                    navigate_to_week(page, week_date)

                print("  Loading rides...")
                click_load_more(page)

                urls = get_trip_urls(page)
                print(f"  Found {len(urls)} trips")

                if not urls:
                    empty += 1
                    if empty >= 3:
                        print("3 empty weeks. Done.")
                        break
                else:
                    empty = 0

                trips = []
                for i, url in enumerate(urls, 1):
                    print(f"  Scraping {i}/{len(urls)}...", end="\r")
                    try:
                        if check_for_security_challenge(page):
                            wait_for_security_clear(page)
                        page.goto(url)
                        page.wait_for_load_state("networkidle")
                        random_delay(0.5, 1.5)
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

                # Advance to next week
                week_date = week_date + timedelta(days=7)
                if week_date > datetime.now():
                    print("Next week is in the future. Done.")
                    break

                # Navigate back to activities and type the next week
                page.goto("https://drivers.uber.com/earnings/activities")
                page.wait_for_load_state("networkidle")
                random_delay(1, 2)
                navigate_to_week(page, week_date)

            except Exception as e:
                print(f"Error: {e}")
                resp = input("Enter to retry, 'skip', or 'stop': ")
                if resp == 'stop':
                    break
                elif resp == 'skip':
                    week_date = week_date + timedelta(days=7)
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