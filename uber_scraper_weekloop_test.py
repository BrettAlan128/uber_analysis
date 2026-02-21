"""Week Loop Navigation Test

Tests ONLY the Previous button week navigation and Load More.
Does NOT scrape trip details — just counts trips found per week.
"""

import random
import time
from playwright.sync_api import sync_playwright

BROWSER_PROFILE_DIR = "browser_profile"


def random_delay(min_sec=1, max_sec=3):
    time.sleep(random.uniform(min_sec, max_sec))


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


def get_week_display(page) -> str:
    try:
        el = page.locator("text=/[A-Z][a-z]{2} \\d+.*–.*\\d{4}/").first
        return el.inner_text(timeout=3000)
    except:
        return "Unknown"


def click_previous_week(page) -> bool:
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


def main():
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    profile = os.path.join(script_dir, BROWSER_PROFILE_DIR)

    print("")
    print("=" * 50)
    print("WEEK LOOP TEST — navigation only, no scraping")
    print("=" * 50)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(profile, headless=False,
            viewport={"width": 1280, "height": 900}, slow_mo=50)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://drivers.uber.com/earnings/activities")

        print("")
        print("Log in, complete security, navigate to starting week.")
        input("Press Enter when ready...")

        week_num = 0
        empty_streak = 0

        while True:
            week_num += 1
            week_text = get_week_display(page)
            print(f"\n--- Week {week_num}: {week_text} ---")

            if check_for_security_challenge(page):
                wait_for_security_clear(page)
                page.goto("https://drivers.uber.com/earnings/activities")
                page.wait_for_load_state("networkidle")
                random_delay(2, 3)

            print("  Loading rides...")
            click_load_more(page)

            urls = get_trip_urls(page)
            print(f"  Found {len(urls)} trips (not scraping)")

            if not urls:
                empty_streak += 1
                if empty_streak >= 3:
                    print("3 empty weeks in a row. Stopping.")
                    break
            else:
                empty_streak = 0

            print("  Clicking Previous...")
            if not click_previous_week(page):
                print("  Previous button not found!")
                resp = input("  Navigate manually + Enter, or type 'stop': ")
                if resp.lower() == 'stop':
                    break

        print("")
        print("=" * 50)
        print(f"Test complete. Navigated {week_num} weeks.")
        print("=" * 50)
        ctx.close()


if __name__ == "__main__":
    main()
