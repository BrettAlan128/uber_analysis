# Path to Chrome executable (update if necessary)
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROMEDRIVER_PATH = r"C:\chromedriver\chromedriver.exe"  # Update with the correct path

# Chrome Debugging Port
DEBUG_PORT = "9222"

# Function to launch Chrome in Debugger Mode
def start_chrome_debugger():
    chrome_command = f'"{CHROME_PATH}" --remote-debugging-port={DEBUG_PORT} --user-data-dir="C:\\selenium\\ChromeProfile"'
    
    # Start Chrome in debugging mode
    subprocess.Popen(chrome_command, shell=True)
    time.sleep(5)  # Wait a few seconds for Chrome to launch

# Function to initialize Selenium WebDriver with Debugger Mode
def init_selenium():
    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", f"localhost:{DEBUG_PORT}")
    
    service = Service(CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    return driver

# Function to handle the "Don't Sign In" popup
def handle_dont_sign_in(driver):
    try:
        dont_sign_in_button = driver.find_element(By.XPATH, "//button[contains(text(), \"Don't sign in\")]")
        dont_sign_in_button.click()
        print("Clicked 'Don't Sign In'")
    except:
        print("No 'Don't Sign In' prompt found.")

# Function to navigate to Uber Driver Portal
def navigate_to_uber(driver):
    driver.get("https://drivers.uber.com")
    print("Navigated to Uber Driver Portal")

# Main Execution
start_chrome_debugger()  # Start Chrome in debugger mode
driver = init_selenium()  # Attach Selenium to the Chrome session
handle_dont_sign_in(driver)  # Handle popups
navigate_to_uber(driver)  # Navigate to Uber

# Keep browser open for manual interaction
time.sleep(10)

# Uncomment this line if you want to close the browser automatically
# driver.quit()





def select_month(driver, month_name):
    """Selects the specified month from the dropdown."""
    try:
        # Click the month button to open dropdown
        month_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, 'Month')]"))
        )
        month_button.click()
        print("✅ Opened month dropdown.")

        # Wait for the month list to be present
        month_list = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, f"//li[contains(text(), '{month_name}')]"))
        )

        # Click using JavaScript if normal click fails
        driver.execute_script("arguments[0].click();", month_list)
        print(f"✅ Selected month: {month_name}.")

    except Exception as e:
        print(f"❌ Error selecting month: {month_name}.", e)

def select_year(driver, year):
    """Selects the specified year from the dropdown."""
    try:
        # Click the year button to open dropdown
        year_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, 'Year')]"))
        )
        year_button.click()
        print("✅ Opened year dropdown.")

        # Wait for the year list to be present
        year_option = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, f"//li[text()='{year}']"))
        )

        # Click using JavaScript if normal click fails
        driver.execute_script("arguments[0].click();", year_option)
        print(f"✅ Selected year: {year}.")

    except Exception as e:
        print(f"❌ Error selecting year: {year}.", e)


def select_day(driver, target_day):
    """
    Selects a day from the currently displayed calendar.
    Example: target_day = "3"
    """
    try:
        # Construct XPath to find the gridcell with a child div that exactly matches the target day.
        day_xpath = f"//div[@role='gridcell' and .//div[normalize-space(text())='{target_day}']]"
        
        # Wait for the day element to be present
        selected_day = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, day_xpath))
            EC.element_to_be_clickable((By.XPATH, day_xpath))
        )
        
        # Click the day element
        selected_day.click()
        print(f"✅ Selected day: {target_day}.")
        
    except Exception as e:
        print(f"❌ Error selecting day: {target_day}.", e)