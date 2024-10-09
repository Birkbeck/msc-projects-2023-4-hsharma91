import json
import time
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor
from elsapy.elsclient import ElsClient
from elsapy.elssearch import ElsSearch
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.firefox import GeckoDriverManager

## Load configuration
con_file = open("config.json")  # Place your Elsevier key in this file
config = json.load(con_file)
con_file.close()

## Initialise client
client = ElsClient(config['apikey'])

# Config for selenium browser
options = Options()
# options.add_argument('--headless')

# List of attack types
attack_list = [
    # 'Ransomware',
    # 'Cryptojack*',
    # 'WannaCry AND (Ransomware OR Attack)',
    # '"Data Poisoning"',
    # 'Deepfake',
    # 'IoT Device Attack',
    'Adversarial Attack'
]

# List of mentions corresponding to attack types
mention_list = [
    
    # ('Ransomware',),
    # ('Cryptojack',),
    # ('WannaCry',),
    # ('Data Poisoning',),
    # ('Deepfake',),
    # ('IoT Device','IoT Attack','Attack on IoT','Attack the IoT'), 
    ('Adversarial Attack',)   

]

years_list = list(range(2023, 2024))
month_list = ['January', 'February','March']
empty = 'Result set was empty'
search_results_list = []

# Initialize browser instances
browser_pool = []
pool_lock = Lock()

def initialize_browsers(n):
    for _ in range(n):
        driver = webdriver.Firefox(options=options, service=Service(GeckoDriverManager().install()))
        driver.get("https://www.scopus.com")  # Navigate to login page
        time.sleep(50)
        input("Please log in to Scopus and press Enter...")
        
        cookies = driver.get_cookies()  # Save cookies after login
        browser_pool.append(driver)

# Function to perform Scopus search
def perform_search(year, month, attack):
    print(f"Searching for {attack} in {month} {year}...")
    doc_srch = ElsSearch(f"TITLE({attack}) OR ABS({attack}) OR KEY({attack}) AND PUBDATETXT({month} {year})", 'scopus')
    doc_srch.execute(client, get_all=True)
    return doc_srch.results

# Function to load page and fetch data
def fetch_data(url, driver):
    try:
        print(f"Loading page: {url}")
        driver.get(url)
        WebDriverWait(driver, 40).until(EC.presence_of_element_located((By.CLASS_NAME, 'Highlight-module__akO5D')))
        print(f"Successfully loaded page: {url}")
        WebDriverWait(driver, 7).until(EC.element_to_be_clickable((By.XPATH, "(//button/span[text()='Indexed keywords'])[1]|(//button/span[text()='Author keywords'])[1]")))
        print("Indexed keywords found, clicking...")
        keyword_element  = driver.find_elements(By.XPATH, "(//button/span[text()='Indexed keywords'])[1]|(//button/span[text()='Author keywords'])[1]")
        if len(keyword_element)==1:
            keyword_element[0].click()
        else:
            keyword_element[1].click()
        time.sleep(2)
        text_elements = driver.find_elements(By.CLASS_NAME, "Highlight-module__akO5D")
        return [element.text for element in text_elements]
    except Exception as e:
        print(f"Error processing URL {url}: {e}")
        
        return []

# Function to process URLs for a particular attack type within a month
def process_urls(urls, driver, mention):
    total_count = 0
    for url in urls:
        text_elements = fetch_data(url, driver)
        total_count += count_mentions(text_elements, mention)
    return total_count

# Function to count mentions in the text
def count_mentions(text_elements, mention):
    totalQ = 0
    for element_text in text_elements:
        element_text = element_text.upper()
        totalQ += sum(element_text.replace("-", " ").count(x.upper().replace("-", " ")) for x in mention)
    return totalQ

# Function to handle attack type processing in a thread
def handle_attack(attack_index, year, month):
    mention = mention_list[attack_index]
    attack = attack_list[attack_index]
    
    print(f"Processing {attack} in {month} {year}...")
    
    # Perform search
    search_results = perform_search(year, month, attack)
    urls = [result['link'][2]['@href'] for result in search_results if 'link' in result and len(result['link']) > 2]
    
    # Get a browser instance from the pool
    with pool_lock:
        driver = browser_pool.pop(0)
    
    # Process the URLs
    total_mentions = process_urls(urls, driver, mention)
    print(f"Total mentions for {attack} in {month} {year}: {total_mentions}")

    
    # Return the browser instance to the pool
    with pool_lock:
        browser_pool.append(driver)
    return total_mentions
    

# Part 1 - Collect the URLs of all relevant documents (for each month and each attack type)
def collect_search_results():
    global search_results_list
    
    for year in years_list:
        print("Searching in year:", str(year))
        
        for month in month_list:

            # Skip irrelevant months for 2011
            if year == 2024 and month in month_list[3:]:
                continue

            print("Searching in year/month:", str(year), "/", month)

            results_for_month = []

            with ThreadPoolExecutor(max_workers=2) as executor:
                results= executor.map(handle_attack, range(len(attack_list)), [year]*len(attack_list), [month]*len(attack_list))
                results_for_month.extend(results)
            # Write all results for the month to the file in a single line
            with open('Attacks_NoM.txt', 'a') as file_object:
                for ii, item in enumerate(results_for_month):
                    file_object.write(str(item))
                    if ii < len(results_for_month) - 1:
                        file_object.write("\t")
                file_object.write("\n")            

# Main execution
if __name__ == "__main__":
    max_threads = 1  # Number of browser windows (threads)
    initialize_browsers(max_threads)  # Initialize the browser instances with login

    collect_search_results()  # Collect all search results using multithreading for I/O-bound tasks

    for driver in browser_pool:
        driver.quit()  # Close all browsers once done
