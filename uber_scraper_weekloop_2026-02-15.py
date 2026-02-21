"""
Uber Driver Trip Scraper
========================

This script uses Playwright to log into an Uber Driver account and export
each trip’s details into a CSV file. It demonstrates how to handle
authentication, including optional two‑factor (2FA), navigate to weekly
activity pages, open the fare breakdown for each ride, parse the fare
components, and write them to a CSV.

**Disclaimers**

* The selectors used in this script are placeholders and may need to be
  updated to match the current Uber Driver web interface. You should
  inspect the page with your browser’s developer tools to find stable
  selectors (e.g. `data-test` attributes or ARIA labels).
* Always respect Uber’s Terms of Service and privacy policies. This script
  accesses personal data and is intended for educational purposes.
* You must set `UBER_PHONE` environment variable (or it defaults to 5039010869).
  The script will use your phone number to log in and handle SMS verification
  automatically by prompting you for the code sent to your phone.
  You can optionally set `UBER_TOTP_SECRET` (a base32 2FA secret) to auto‑
  generate codes; otherwise the script prompts you to enter codes manually.
"""

import asyncio
import csv
import json
import os
import re
from pathlib import Path

try:
    import pyotp  # type: ignore
except ImportError:
    pyotp = None

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


CSV_FILENAME = Path("uber_trips.csv")
VISITED_FILENAME = Path("visited.jsonl")


def parse_fare_line(item_label: str, text: str) -> dict:
    """Parse a line from the fare breakdown for distance/time.

    Given a label (e.g. "Distance", "Time") and the accompanying details
    string (e.g. "1.64 mile × $0.99/mile (rounding applied)"), return a
    dictionary containing any parsed components.

    Returns a dictionary with keys:
      - miles: float distance (if present)
      - minutes: float time in minutes (if present)
      - rate_per_mile: float per mile rate (if present)
      - rate_per_minute: float per minute rate (if present)
    """
    result: dict = {}
    mile_match = re.search(
        r"([\d\.]+)\s*mile\s*×\s*\$([\d\.]+)/mile",
        text,
        re.IGNORECASE,
    )
    if mile_match:
        miles = float(mile_match.group(1))
        rate_per_mile = float(mile_match.group(2))
        result["miles"] = miles
        result["rate_per_mile"] = rate_per_mile
    minute_match = re.search(
        r"([\d\.]+)\s*min(?:ute)?\s*×\s*\$([\d\.]+)/min",
        text,
        re.IGNORECASE,
    )
    if minute_match:
        minutes = float(minute_match.group(1))
        rate_per_minute = float(minute_match.group(2))
        result["minutes"] = minutes
        result["rate_per_minute"] = rate_per_minute
    return result


async def get_2fa_code() -> str:
    """Return a 2FA code either from the env or user input."""
    secret = os.environ.get("UBER_TOTP_SECRET")
    if secret and pyotp:
        totp = pyotp.TOTP(secret)
        return totp.now()
    # Prompt user for code when not available automatically
    return input("Enter Uber 2FA code (SMS or Authenticator): ").strip()


async def login_and_navigate(page) -> None:
    """Log into Uber Driver and navigate to the Activity page."""
    phone = os.environ.get("UBER_PHONE", "5039010869")
    if not phone:
        raise RuntimeError("UBER_PHONE environment variable must be set.")

    # Navigate to login page
    await page.goto("https://drivers.uber.com/login")
    
    # Try to find phone number input field first
    phone_input_found = False
    phone_selectors = [
        "input[type='tel']",
        "input[placeholder*='phone']",
        "input[placeholder*='Phone']",
        "input[name='phone']",
        "input[name='phoneNumber']",
        "input[inputmode='tel']"
    ]
    
    for selector in phone_selectors:
        try:
            if await page.locator(selector).count() > 0:
                print(f"✓ Phone number field found: {selector}")
                await page.fill(selector, phone)
                phone_input_found = True
                break
        except:
            continue
    
    # If no phone field found, try email field (some pages might accept phone in email field)
    if not phone_input_found:
        print("No phone field found, trying email field...")
        try:
            await page.fill("input[type=email]", phone)
            phone_input_found = True
        except:
            pass
    
    if not phone_input_found:
        raise RuntimeError("Could not find phone number or email input field")
    
    # Submit the form
    await page.click("button[type=submit]")
    
    # Wait for verification step - focus on SMS, skip puzzles
    print("Waiting for verification step...")
    
    # Wait a bit for any redirects to complete
    await page.wait_for_timeout(3000)
    
    # Check if we're on an auth page that might have verification
    current_url = page.url
    if "auth.uber.com" in current_url:
        print(f"✓ On authentication page: {current_url}")
        print("Waiting for SMS verification...")
        
        # Wait a bit more for SMS field to appear
        await page.wait_for_timeout(2000)
    else:
        print("✓ Not on auth page, proceeding...")
    
    # Check for SMS verification - wait longer and check more thoroughly
    print("Checking for SMS verification...")
    
    # Wait longer for SMS field to appear (sometimes it takes time)
    await page.wait_for_timeout(5000)
    
    try:
        # Wait for SMS code input field with multiple possible selectors
        sms_selectors = [
            "input[name=otp]",
            "input[placeholder*='code']",
            "input[placeholder*='Code']",
            "input[type='tel']",
            "input[inputmode='numeric']",
            "input[placeholder*='verification']",
            "input[placeholder*='Verification']",
            "input[placeholder*='SMS']",
            "input[placeholder*='sms']",
            "input[placeholder*='text']",
            "input[placeholder*='Text']"
        ]
        
        sms_field_found = False
        sms_selector = None
        
        # Try each selector with a longer timeout
        for selector in sms_selectors:
            try:
                await page.wait_for_selector(selector, timeout=10000)
                print(f"✓ SMS verification field detected: {selector}")
                sms_field_found = True
                sms_selector = selector
                break
            except PlaywrightTimeoutError:
                continue
        
        # If no specific SMS field found, check for any input that might be for codes
        if not sms_field_found:
            print("No specific SMS field found, checking for any code input...")
            try:
                # Look for any input field that might be for verification codes
                all_inputs = await page.locator("input").all()
                for i, inp in enumerate(all_inputs):
                    input_type = await inp.get_attribute("type")
                    input_placeholder = await inp.get_attribute("placeholder") or ""
                    input_name = await inp.get_attribute("name") or ""
                    
                    # Check if this looks like a code input
                    if (input_type in ["tel", "text", "number"] and 
                        any(keyword in input_placeholder.lower() for keyword in ["code", "verification", "sms", "text", "otp"]) or
                        any(keyword in input_name.lower() for keyword in ["code", "otp", "verification"])):
                        print(f"✓ Found potential code input: type='{input_type}', placeholder='{input_placeholder}', name='{input_name}'")
                        sms_field_found = True
                        sms_selector = f"input:nth-of-type({i+1})"
                        break
            except Exception as e:
                print(f"Error checking inputs: {e}")
        
        if sms_field_found:
            print("SMS verification code field detected. Please check your phone for the SMS code.")
            print("You should receive a text message with a verification code.")
            
            # Get SMS code from user
            code = await get_2fa_code()
            await page.fill(sms_selector, code)
            await page.click("button[type=submit]")
            
            # Wait for SMS verification to process
            print("Waiting for SMS verification to process...")
            await page.wait_for_timeout(5000)
        else:
            print("No SMS verification step detected, proceeding...")
            print("Current page elements:")
            try:
                # List all input fields for debugging
                all_inputs = await page.locator("input").all()
                print(f"Found {len(all_inputs)} input fields:")
                for i, inp in enumerate(all_inputs):
                    input_type = await inp.get_attribute("type")
                    input_placeholder = await inp.get_attribute("placeholder") or ""
                    input_name = await inp.get_attribute("name") or ""
                    print(f"  {i+1}: type='{input_type}', placeholder='{input_placeholder}', name='{input_name}'")
            except Exception as e:
                print(f"Error listing inputs: {e}")
        
    except Exception as e:
        print(f"Error during SMS verification: {e}")
        print("Proceeding anyway...")

    # Wait for page to load and look for various possible elements
    print("Waiting for page to load...")
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except PlaywrightTimeoutError:
        print("Page load timeout, but continuing...")
        # Just wait a bit and continue
        await page.wait_for_timeout(3000)
    
    # Take a screenshot for debugging
    await page.screenshot(path="debug_login.png")
    print("Screenshot saved as debug_login.png for debugging")
    
    # Try multiple ways to find and navigate to Activity page
    activity_found = False
    
    # Method 1: Look for "Activity Details" text
    try:
        await page.wait_for_selector("text=Activity Details", timeout=5000)
        print("Found 'Activity Details' text directly")
        activity_found = True
    except PlaywrightTimeoutError:
        pass
    
    # Method 2: Look for "Activity" tab/link
    if not activity_found:
        try:
            await page.click("text=Activity", timeout=5000)
            await page.wait_for_selector("text=Activity Details", timeout=10000)
            print("Clicked 'Activity' tab and found details")
            activity_found = True
        except PlaywrightTimeoutError:
            pass
    
    # Method 3: Look for any activity-related elements
    if not activity_found:
        try:
            # Try different possible selectors for activity
            selectors = [
                "a[href*='activity']",
                "button:has-text('Activity')",
                "[data-test*='activity']",
                "text=Trips",
                "text=History"
            ]
            for selector in selectors:
                try:
                    await page.click(selector, timeout=3000)
                    await page.wait_for_load_state("networkidle", timeout=5000)
                    print(f"Clicked selector: {selector}")
                    activity_found = True
                    break
                except PlaywrightTimeoutError:
                    continue
        except Exception as e:
            print(f"Error trying alternative selectors: {e}")
    
    if not activity_found:
        print("Could not find Activity page. Current page URL:", page.url)
        print("Page title:", await page.title())
        # Don't raise error, just continue and see what happens
        print("Continuing anyway...")


async def fetch_visited() -> set:
    """Load previously visited trip IDs from the checkpoint file."""
    visited: set = set()
    if VISITED_FILENAME.exists():
        with VISITED_FILENAME.open("r", encoding="utf-8") as f:
            for line in f:
                trip_id = line.strip()
                if trip_id:
                    visited.add(trip_id)
    return visited


async def append_visited(trip_id: str) -> None:
    """Append a trip ID to the visited checkpoint file."""
    with VISITED_FILENAME.open("a", encoding="utf-8") as f:
        f.write(trip_id + "\n")


async def write_csv_header_if_needed() -> None:
    """Write header row to CSV if it doesn't exist."""
    if not CSV_FILENAME.exists():
        with CSV_FILENAME.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "ride_id",
                "date_local",
                "pickup_time_local",
                "dropoff_time_local",
                "event_type",
                "distance_miles",
                "total_trip_time_minutes",
                "pickup_location",
                "dropoff_location",
                "fare_breakdown_json",
                "rate_per_mile",
                "rate_per_minute",
                "total_fare",
            ])


async def append_trip_row(row: list) -> None:
    """Append a row to the CSV file."""
    with CSV_FILENAME.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(row)


async def scrape_trip_details(context, trip_link: str, visited: set) -> None:
    """Open a trip in a new tab, parse details, and write to CSV."""
    trip_id = trip_link.split("/")[-1].split("?")[0]
    if trip_id in visited:
        return
    page = await context.new_page()
    try:
        await page.goto(trip_link)
        await page.wait_for_load_state("networkidle")

        # Expand fare breakdown if necessary (arrow button near "Fare")
        try:
            await page.click(
                "button:has-text('Fare') >> svg, button[aria-label='Expand fare'], div:has(svg[aria-label='expand'])",
                timeout=4000,
            )
        except PlaywrightTimeoutError:
            pass

        # Extract date and times; adjust selectors as needed
        date_elem = await page.text_content("[data-test=trip-date]")
        pickup_time = await page.text_content("[data-test=pickup-time]")
        dropoff_time = await page.text_content("[data-test=dropoff-time]")
        event_type = (await page.text_content("[data-test=trip-type]")) or ""
        pickup_loc = await page.text_content("[data-test=pickup-location]") or ""
        dropoff_loc = await page.text_content("[data-test=dropoff-location]") or ""

        # Fare item selectors (labels, values, details). These may need adjustment.
        labels = await page.locator("[data-test=fare-item-label]").all_text_contents()
        values = await page.locator("[data-test=fare-item-value]").all_text_contents()
        details = await page.locator("[data-test=fare-item-details]").all_text_contents()
        fare_breakdown: dict = {}
        total_fare: float = 0.0
        distance_miles: float | None = None
        total_trip_minutes: float | None = None
        rate_per_mile: float | None = None
        rate_per_minute: float | None = None
        for lbl, val_str, detail in zip(labels, values, details):
            val_clean = val_str.replace("$", "").replace(",", "").strip()
            try:
                val = float(val_clean) if val_clean else None
            except ValueError:
                val = None
            fare_breakdown[lbl] = {"value": val, "detail": detail}
            if val is not None:
                total_fare += val
            parsed = parse_fare_line(lbl, detail)
            if parsed.get("miles") is not None:
                distance_miles = (distance_miles or 0.0) + parsed["miles"]
            if parsed.get("minutes") is not None:
                total_trip_minutes = (total_trip_minutes or 0.0) + parsed["minutes"]
            if parsed.get("rate_per_mile") and (rate_per_mile is None or parsed["rate_per_mile"] > 0):
                rate_per_mile = parsed["rate_per_mile"]
            if parsed.get("rate_per_minute") and (rate_per_minute is None or parsed["rate_per_minute"] > 0):
                rate_per_minute = parsed["rate_per_minute"]

        # Normalize date/time strings (strip whitespace)
        date_local = date_elem.strip() if date_elem else ""
        pickup_time_local = pickup_time.strip() if pickup_time else ""
        dropoff_time_local = dropoff_time.strip() if dropoff_time else ""

        row = [
            trip_id,
            date_local,
            pickup_time_local,
            dropoff_time_local,
            event_type.strip(),
            distance_miles,
            total_trip_minutes,
            pickup_loc.strip(),
            dropoff_loc.strip(),
            json.dumps(fare_breakdown, ensure_ascii=False),
            rate_per_mile,
            rate_per_minute,
            total_fare,
        ]
        await append_trip_row(row)
        await append_visited(trip_id)
        print(f"Scraped trip {trip_id}")
    finally:
        await page.close()


async def scrape_all_trips() -> None:
    """Main entry: log in, iterate over weeks, and scrape all visible trips."""
    visited = await fetch_visited()
    await write_csv_header_if_needed()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await login_and_navigate(page)

        # Loop through weeks using a "Previous" button until none exists
        while True:
            # Collect all trip detail URLs on the current week's activity table
            trip_links: list[str] = []
            try:
                view_buttons = page.locator("text='View Details'")
                count = await view_buttons.count()
                for i in range(count):
                    button = view_buttons.nth(i)
                    href = await button.get_attribute("href")
                    if href:
                        trip_links.append(href)
            except PlaywrightTimeoutError:
                pass

            for link in trip_links:
                try:
                    await scrape_trip_details(context, link, visited)
                except Exception as exc:
                    print(f"Error scraping {link}: {exc}")

            # Attempt to click the "Previous" week button to move back in time
            try:
                prev_button = page.locator("button:has-text('Previous')")
                if await prev_button.is_visible():
                    await prev_button.click()
                    await page.wait_for_load_state("networkidle")
                    continue
            except PlaywrightTimeoutError:
                pass
            break  # no previous button; exit loop

        await browser.close()


def main() -> None:
    asyncio.run(scrape_all_trips())


if __name__ == "__main__":
    main()