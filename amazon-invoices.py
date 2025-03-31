"""
Amazon Order Invoice Downloader

This script automates the process of retrieving order information from Amazon and organizing
invoices into a folder structure by month-year.

Features:
- Automated login to Amazon (email from .env file, manual password entry)
- Extract order details (date, order ID, product titles)
- Create a folder structure for organizing invoices (Amazon/MM-YYYY/)
- Assist with downloading invoices to the appropriate folders

Usage:
1. Create a .env file with AMAZON_EMAIL=your_email@example.com
2. Run the script: python amazon-invoices.py
3. When prompted, manually enter your password in the browser window
4. The script will extract order details and create folders
5. Follow the on-screen instructions to manually download invoices

Requirements:
- Python 3.7+
- browser-use package
- Optional: python-dotenv, langchain packages

Notes:
- This script handles different date formats (e.g., "13 March 2023", "2023-03-13")
- It skips non-product orders (like Amazon Prime Video)
- The script provides guidance for manual invoice downloads if automated download fails
"""

import asyncio
import os
import sys
import re
from pathlib import Path
import json
from datetime import datetime
import hashlib

# Try to import optional dependencies, with graceful fallbacks
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: python-dotenv not found. Environment variables will not be loaded from .env file.")
    def load_dotenv():
        pass

try:
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(
        model='gpt-4o',
        temperature=0.0,
    )
    LLM_AVAILABLE = True
except ImportError:
    print("Warning: langchain_openai not found. LLM features will be disabled.")
    llm = None
    LLM_AVAILABLE = False

try:
    from langchain_core.messages import HumanMessage, SystemMessage
    LANGCHAIN_CORE_AVAILABLE = True
except ImportError:
    print("Warning: langchain_core not found. LLM features will be disabled.")
    LANGCHAIN_CORE_AVAILABLE = False

try:
    from browser_use.browser.browser import Browser, BrowserConfig, BrowserContextConfig
    BROWSER_USE_AVAILABLE = True
except ImportError:
    print("Error: browser_use package not found. This script requires the browser_use package.")
    print("Please make sure you're running this script in the browser-use repository environment.")
    sys.exit(1)

# Setup browser
browser = Browser(
    config=BrowserConfig(
        new_context_config=BrowserContextConfig(
            viewport_expansion=-1,
            highlight_elements=False,
        ),
    ),
)

#task = 'go to https://web.snelstart.nl/login?_fs=16808665754-15527498668&_fsRef=https%3A%2F%2Fwww.snelstart.nl%2F and click on buttons on the wikipedia page to go as fast as possible from banna to Quantum mechanics'

#agent = Agent(task=task, llm=llm, browser=browser, use_vision=False)

async def manual_login():
    """Login to Amazon using email from .env file and allowing manual password entry."""
    # Get email from environment variables
    email = os.getenv('AMAZON_EMAIL')
    
    if not email:
        print("Error: AMAZON_EMAIL environment variable not set.")
        print("Please set this in your .env file or as environment variables.")
        return None, None
    
    # Create a new context
    context = await browser.new_context()
    
    # Create a new tab 
    await context.create_new_tab()
    
    # Navigate directly to Amazon Orders page in English
    print("Navigating to Amazon Orders page...")
    await context.navigate_to("https://www.amazon.nl/your-orders/orders?ref_=nav_orders_first&language=en_GB")
    
    # Get the current page after navigation
    page = await context.get_current_page()
    
    try:
        # Wait for the sign-in page to load
        print("Waiting for sign-in page...")
        await page.wait_for_url("**/ap/signin**", timeout=10000)
        print("On sign-in page - filling email...")
        
        # Fill in the email field
        await page.fill("#ap_email", email)
        
        # Click continue
        await page.click("#continue")
        
        print("Please enter your password manually in the browser window.")
        print("The browser will remain open for you to complete the login process.")
        
        # Wait for user to manually enter password and complete login
        # We don't know exactly when the user will finish, so we'll check regularly
        print("Waiting for you to complete login and reach the orders page...")
        
        login_wait_time = 120  # 2 minutes total
        check_interval = 5  # Check every 5 seconds
        
        for _ in range(login_wait_time // check_interval):
            current_url = page.url
            print(f"Current URL: {current_url}")
            
            # Check if we've reached the orders page
            if "your-orders" in current_url or "order-history" in current_url:
                print("Successfully logged in and reached the orders page!")
                break
            
            await asyncio.sleep(check_interval)
        
    except TimeoutError as e:
        print(f"Timeout during login process: {e}")
    except ValueError as e:
        print(f"Value error during login: {e}")
    except RuntimeError as e:
        print(f"Runtime error during login: {e}")
    
    return page, context

async def extract_order_details(page):
    """Extract order details (date, order ID, product title) from the orders page."""
    print("\n--- ATTEMPTING TO EXTRACT ORDER DETAILS ---\n")
    
    try:
        print("Ensuring we're on the correct page with orders...")
        current_url = page.url
        
        # If not on orders page, navigate there
        if not ("your-orders" in current_url or "order-history" in current_url):
            print(f"Not on orders page. Current URL: {current_url}")
            print("Navigating to orders page...")
            await page.goto("https://www.amazon.nl/your-orders/orders?ref_=nav_orders_first&language=en_GB")
            await page.wait_for_load_state("networkidle")
            print("Navigation complete. Now on: " + page.url)
        
        # Wait for any order boxes to appear with a long timeout
        print("Waiting for order boxes to appear (up to 20 seconds)...")
        try:
            await page.wait_for_selector(".a-box-group", timeout=20000)
            print("Order boxes found!")
        except Exception as e:
            print(f"Could not find order boxes. Error: {e}")
            print("No order boxes found on the page.")
            return []
        
        # Get all order boxes on the page
        print("Looking for all order boxes...")
        all_order_boxes = await page.query_selector_all(".a-box-group")
        print(f"Found {len(all_order_boxes)} total order boxes")
        
        orders_data = []
        valid_orders_count = 0
        
        # Process each order box
        for i, box in enumerate(all_order_boxes):
            try:
                print(f"Examining order box #{i+1}...")
                
                # First, check if this is a valid product order (not Prime Video)
                # Valid orders should have product titles
                title_elements = await box.query_selector_all(".yohtmlc-product-title")
                if not title_elements or len(title_elements) == 0:
                    print(f"  Skipping order #{i+1} - no product titles found (likely not a regular product order)")
                    continue
                
                # Get the date
                date_element = await box.query_selector(".a-column.a-span3 .a-size-base.a-color-secondary")
                date = await page.evaluate("el => el.textContent.trim()", date_element) if date_element else None
                
                # Skip if date not found
                if not date:
                    print(f"  Skipping order #{i+1} - no date found")
                    continue
                
                print(f"  Found date: {date}")
                
                # Get the order ID
                order_id_container = await box.query_selector(".yohtmlc-order-id")
                if not order_id_container:
                    print(f"  Skipping order #{i+1} - no order ID found")
                    continue
                
                # Extract order ID, trying different methods
                order_id_span = await order_id_container.query_selector("span.a-color-secondary:not(.a-text-caps)")
                if order_id_span:
                    order_id = await page.evaluate("el => el.textContent.trim()", order_id_span)
                else:
                    # Fallback: try to get all text and parse it
                    raw_text = await page.evaluate("el => el.textContent.trim()", order_id_container)
                    # Try to remove "Order #" from the beginning if present
                    order_id = raw_text.replace("Order #", "").strip()
                
                # Skip if order ID is just "Order #" or empty
                if not order_id or order_id == "Order #" or len(order_id) < 3:
                    print(f"  Skipping order #{i+1} - invalid order ID: {order_id}")
                    continue
                
                print(f"  Found order ID: {order_id}")
                
                # Get product titles
                titles = []
                for title_el in title_elements:
                    title_text = await page.evaluate("el => el.textContent.trim()", title_el)
                    if title_text and len(title_text) > 0:
                        titles.append(title_text)
                
                # Skip if no valid product titles
                if not titles:
                    print(f"  Skipping order #{i+1} - no valid product titles")
                    continue
                
                print(f"  Found {len(titles)} products")
                
                # This is a valid order - increment counter
                valid_orders_count += 1
                
                # Create a data structure for this order
                order_data = {
                    "date": date,
                    "order_id": order_id,
                    "products": titles
                }
                
                orders_data.append(order_data)
                
                # Print order details
                print(f"Valid Order #{valid_orders_count}:")
                print(f"  Date: {date}")
                print(f"  Order ID: {order_id}")
                print("  Products:")
                for title in titles:
                    print(f"    - {title}")
                print()
                
            except Exception as e:
                print(f"Error processing order box #{i+1}: {e}")
        
        print(f"Successfully extracted data from {len(orders_data)} valid product orders")
        print(f"Skipped {len(all_order_boxes) - valid_orders_count} invalid or non-product orders")
        return orders_data
        
    except TimeoutError as e:
        print(f"Timeout waiting for order boxes to appear: {e}")
        print("Are you on the correct page?")
    except Exception as e:
        print(f"Error extracting order details: {e}")
    
    return []

def create_folder_structure(orders_data):
    """
    Create a folder structure for Amazon orders:
    - Main 'Amazon' folder
    - Subfolders for each month-year (mm-yyyy)
    
    Returns a dictionary mapping month-year to folder paths.
    """
    print("\n--- CREATING FOLDER STRUCTURE ---\n")
    
    # Create main Amazon folder in current directory
    amazon_folder = Path("Amazon")
    if not amazon_folder.exists():
        print(f"Creating main Amazon folder: {amazon_folder}")
        amazon_folder.mkdir()
    else:
        print(f"Amazon folder already exists: {amazon_folder}")
    
    # Dictionary to track month-year folders
    month_year_folders = {}
    
    # Process each order and create appropriate folders
    for order in orders_data:
        # Parse the date from the order to get month and year
        date_str = order["date"]
        try:
            # Handle different date formats that might appear
            # First try common formats like "13 March 2023" (day month year)
            try:
                # Try European format (day month year)
                match = re.search(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', date_str)
                if match:
                    # We don't need the day value for folder naming, so we can use _ as a placeholder
                    _, month_name, year = match.groups()
                    # Convert month name to month number
                    month_names = ["January", "February", "March", "April", "May", "June", 
                                  "July", "August", "September", "October", "November", "December"]
                    month_names_lower = [m.lower() for m in month_names]
                    month_num = month_names_lower.index(month_name.lower()) + 1
                    
                    # Format as mm-yyyy
                    month_year = f"{month_num:02d}-{year}"
                else:
                    # Try other formats like "2023-03-13" (yyyy-mm-dd)
                    match = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_str)
                    if match:
                        year, month, _ = match.groups()  # Use _ for day as we don't need it
                        month_year = f"{month}-{year}"
                    else:
                        print(f"  Could not parse date format: {date_str}, using 'unknown' as folder")
                        month_year = "unknown"
            except ValueError:
                # If the above parsing fails
                print(f"  Error parsing date: {date_str}, using 'unknown' as folder")
                month_year = "unknown"
                
            # Create month-year folder if it doesn't exist
            if month_year not in month_year_folders:
                month_year_folder = amazon_folder / month_year
                if not month_year_folder.exists():
                    print(f"  Creating folder for {month_year}: {month_year_folder}")
                    month_year_folder.mkdir()
                month_year_folders[month_year] = month_year_folder
                
            folder_path = month_year_folders[month_year]
            print(f"  Order {order['order_id']} will be placed in folder: {folder_path}")
            
        except Exception as e:
            print(f"  Error processing date for order {order['order_id']}: {e}")
            print("  This order will be placed in the main Amazon folder")
    
    print(f"\nCreated {len(month_year_folders)} month-year folders within Amazon folder")
    return month_year_folders

async def download_invoices(page, context, orders_data, month_year_folders):
    """
    Download invoices for each order and save them in the appropriate folders.
    
    Args:
        page: The browser page object
        context: The browser context object
        orders_data: List of order details (date, order_id, products)
        month_year_folders: Dictionary mapping month-year to folder paths
        
    Returns:
        Total number of invoices downloaded
    """
    print("\n--- DOWNLOADING INVOICES ---\n")
    
    # Set longer timeouts to avoid hanging
    page.set_default_timeout(60000)  # 60 seconds for more reliable waiting
    
    # Ensure we're on the orders page
    try:
        current_url = page.url
        print(f"Current page URL: {current_url}")
        
        if not ("your-orders" in current_url or "order-history" in current_url):
            print("Not on orders page. Navigating there...")
            await page.goto("https://www.amazon.nl/your-orders/orders?ref_=nav_orders_first&language=en_GB", 
                           timeout=60000)
            await page.wait_for_load_state("networkidle", timeout=60000)
            print(f"Navigated to orders page: {page.url}")
    except Exception as e:
        print(f"Error navigating to orders page: {e}")
        print("Attempting to continue with current page")
    
    # Track total invoices downloaded
    total_downloaded = 0
    processed_order_ids = set()
    
    # Process each order
    for i, order in enumerate(orders_data):
        order_id = order.get("order_id")
        order_date = order.get("date")
        
        if not order_id or order_id in processed_order_ids:
            print(f"Skipping order #{i+1} - invalid or already processed: {order_id}")
            continue
            
        print(f"\n{'='*40}")
        print(f"Processing order #{i+1}/{len(orders_data)}: {order_id} (Date: {order_date})")
        print(f"{'='*40}")
        
        processed_order_ids.add(order_id)
        
        # Find the order box containing this order ID
        print(f"Looking for order box containing order ID: {order_id}...")
        
        # Get all order boxes
        all_order_boxes = await page.query_selector_all(".a-box-group")
        print(f"Found {len(all_order_boxes)} total order boxes")
        
        order_box = None
        
        # Find the box containing our order ID
        for j, box in enumerate(all_order_boxes):
            try:
                box_text = await page.evaluate("el => el.textContent", box)
                if order_id in box_text:
                    order_box = box
                    print(f"Found order box #{j+1} containing order ID {order_id}")
                    break
            except Exception as e:
                print(f"Error checking order box #{j+1}: {e}")
        
        if not order_box:
            print(f"Could not find order box for order {order_id}")
            continue
        
        # Look for the invoice button
        print("Looking for invoice button...")
        invoice_button = await order_box.query_selector("a.a-link-normal:has-text('Invoice')")
        
        if not invoice_button:
            print(f"No invoice button found for order {order_id}")
            continue
        
        # Make sure any previous popovers are closed
        await close_popover(page)
        
        print("Found invoice button, clicking to open popover menu...")
        try:
            await invoice_button.click()
        except Exception as e:
            print(f"Error clicking invoice button: {e}")
            await page.screenshot(path=f"error_clicking_invoice_{order_id}.png")
            
            # Try to scroll the button into view and click again
            try:
                print("Trying to scroll invoice button into view...")
                await page.evaluate("(el) => el.scrollIntoView({ behavior: 'smooth', block: 'center' })", invoice_button)
                await asyncio.sleep(1)
                await invoice_button.click()
            except Exception as e2:
                print(f"Still couldn't click invoice button: {e2}")
                continue
        
        # Process the invoice popover and download PDFs
        downloaded = await process_invoice_popover(
            page, context, order_id, order_date, month_year_folders
        )
        
        total_downloaded += downloaded
        
        # Wait a moment before processing the next order
        print("Waiting 3 seconds before processing next order...")
        await asyncio.sleep(3)
        
        # Ensure any popover is closed before proceeding to next order
        await close_popover(page)
    
    print(f"\nTotal invoices downloaded: {total_downloaded} from {len(processed_order_ids)} orders")
    return total_downloaded

# Helper function to extract month-year from date string
def get_month_year_from_date(date_str):
    """Extract month-year from date string in various formats."""
    try:
        # Try European format (day month year)
        match = re.search(r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})', date_str)
        if match:
            _, month_name, year = match.groups()
            month_names = ["January", "February", "March", "April", "May", "June", 
                          "July", "August", "September", "October", "November", "December"]
            month_names_lower = [m.lower() for m in month_names]
            month_num = month_names_lower.index(month_name.lower()) + 1
            return f"{month_num:02d}-{year}"
        
        # Try other formats like "2023-03-13" (yyyy-mm-dd)
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_str)
        if match:
            year, month, _ = match.groups()
            return f"{month}-{year}"
    except Exception:
        pass
    
    return "unknown"

async def open_invoice_popover(page, orders_data):
    """
    Focus only on opening the invoice popover for each order and log its content.
    
    Args:
        page: The browser page object
        orders_data: List of order details (date, order_id, products)
    """
    print("\n--- OPENING INVOICE POPOVERS ---\n")
    
    # Set shorter timeouts to avoid hanging
    page.set_default_timeout(60000)  # 60 seconds for more reliable waiting
    
    # Ensure we're on the orders page
    try:
        current_url = page.url
        print(f"Current page URL: {current_url}")
        
        if not ("your-orders" in current_url or "order-history" in current_url):
            print("Not on orders page. Navigating there...")
            await page.goto("https://www.amazon.nl/your-orders/orders?ref_=nav_orders_first&language=en_GB", 
                            timeout=60000)
            await page.wait_for_load_state("networkidle", timeout=60000)
            print(f"Navigated to orders page: {page.url}")
    except Exception as e:
        print(f"Error navigating to orders page: {e}")
        print("Attempting to continue with current page")
    
    # Take a screenshot of the orders page for debugging
    try:
        await page.screenshot(path="orders_page.png")
        print("Saved screenshot of orders page to orders_page.png")
    except Exception as e:
        print(f"Could not save screenshot: {e}")
    
    # Process only one order to focus on debugging
    if not orders_data:
        print("No orders to process")
        return
    
    # Just use the first order for debugging
    order = orders_data[0]
    order_id = order.get("order_id")
    
    print("\n" + "="*40)
    print("FOCUSING ON SINGLE ORDER FOR DEBUGGING")
    print(f"Opening invoice popover for order: {order_id}")
    print("="*40)
    
    # Find the order box containing this order ID
    try:
        print(f"Looking for order box containing order ID: {order_id}...")
        
        # Get all order boxes
        all_order_boxes = await page.query_selector_all(".a-box-group")
        print(f"Found {len(all_order_boxes)} total order boxes")
        
        # Log the text content of first few boxes for debugging
        print("First 3 order boxes content for debugging:")
        for j, box in enumerate(all_order_boxes[:3]):
            try:
                box_text = await page.evaluate("el => el.textContent", box)
                print(f"Box #{j+1} content preview: {box_text[:100]}...")
            except Exception as e:
                print(f"Error getting text for box #{j+1}: {e}")
        
        order_box = None
        
        # Find the box containing our order ID
        for j, box in enumerate(all_order_boxes):
            try:
                box_text = await page.evaluate("el => el.textContent", box)
                if order_id in box_text:
                    order_box = box
                    print(f"Found order box #{j+1} containing order ID {order_id}")
                    break
            except Exception as e:
                print(f"Error checking box #{j+1}: {e}")
        
        if not order_box:
            print(f"Could not find order box for order {order_id}")
            # Taking another approach - try looking for any 'Invoice' links
            print("Looking for any 'Invoice' links on the page...")
            invoice_links = await page.query_selector_all("a.a-link-normal:has-text('Invoice')")
            print(f"Found {len(invoice_links)} invoice links on the page")
            
            if invoice_links:
                print("Using the first invoice link found")
                invoice_button = invoice_links[0]
            else:
                print("No invoice links found on the page")
                return
        else:
            # Look for the invoice button
            print("Looking for invoice button within the order box...")
            invoice_button = await order_box.query_selector("a.a-link-normal:has-text('Invoice')")
            
            if not invoice_button:
                print(f"No invoice button found for order {order_id}")
                return
            
        # Take a screenshot before clicking
        await page.screenshot(path="before_click.png")
        print("Saved screenshot before clicking invoice button")
        
        print("Found invoice button, clicking to open popover menu...")
        await invoice_button.click()
        
        # Wait for the popover to appear
        print("Waiting for invoice popover menu...")
        popover_selector = "div.a-popover-wrapper"
        try:
            await page.wait_for_selector(popover_selector, timeout=10000)
            print("Invoice popover menu appeared")
            
            # Add a delay to ensure the popover content is fully loaded
            print("Waiting 3 seconds for popover content to fully load...")
            await asyncio.sleep(3)
            
            # Take a screenshot to see the popover
            await page.screenshot(path=f"invoice_popover_{order_id}.png")
            print(f"Saved popover screenshot to invoice_popover_{order_id}.png")
            
            # Get the raw HTML of the popover for debugging
            popover = await page.query_selector(popover_selector)
            if popover:
                popover_html = await page.evaluate("el => el.outerHTML", popover)
                # Save the HTML to a file
                with open(f"popover_{order_id}.html", "w", encoding="utf-8") as f:
                    f.write(popover_html)
                print(f"Saved popover HTML to popover_{order_id}.html")
                
                # Get the text content
                popover_text = await page.evaluate("el => el.textContent", popover)
                print(f"Popover text content:\n{popover_text}")
            
            # Find all the items in the popover menu
            invoice_list = await page.query_selector("ul.a-unordered-list.a-vertical.invoice-list")
            
            if not invoice_list:
                print("Could not find invoice list in popover with class 'a-unordered-list a-vertical invoice-list'")
                
                # Try more general selector
                print("Looking for any unordered lists in the popover...")
                ul_elements = await popover.query_selector_all("ul")
                print(f"Found {len(ul_elements)} unordered lists in the popover")
                
                for i, ul in enumerate(ul_elements):
                    ul_text = await page.evaluate("el => el.textContent", ul)
                    ul_html = await page.evaluate("el => el.outerHTML", ul)
                    print(f"UL #{i+1} content: {ul_text}")
                    print(f"UL #{i+1} HTML: {ul_html[:200]}...")  # First 200 chars
                    
                    # Check if this list has li elements
                    li_elements = await ul.query_selector_all("li")
                    print(f"UL #{i+1} has {len(li_elements)} list items")
                    
                    if li_elements:
                        invoice_list = ul
                        break
                
                if not invoice_list:
                    print("Still could not find any suitable list in the popover")
                    
                    # Try a more general selector for popover content
                    print("Looking for div.a-popover-content...")
                    popover_content = await popover.query_selector("div.a-popover-content")
                    if popover_content:
                        content_html = await page.evaluate("el => el.outerHTML", popover_content)
                        print(f"Popover content HTML: {content_html[:300]}...")  # First 300 chars
                    
                    # Just log whatever is in the popover
                    print("Showing all elements in the popover for debugging:")
                    all_elements = await popover.query_selector_all("*")
                    print(f"Found {len(all_elements)} elements in the popover")
                    for i, el in enumerate(all_elements[:10]):  # First 10 elements
                        tag_name = await page.evaluate("el => el.tagName", el)
                        el_text = await page.evaluate("el => el.textContent", el)
                        print(f"Element #{i+1}: <{tag_name}> - {el_text[:50]}...")
                    
                    return
            
            # Now we have invoice_list, get the items
            invoice_items = await invoice_list.query_selector_all("li")
            print(f"Found {len(invoice_items)} items in the invoice list")
            
            # Log each item in the popover
            for j, item in enumerate(invoice_items):
                item_text = await page.evaluate("el => el.textContent.trim()", item)
                item_html = await page.evaluate("el => el.outerHTML", item)
                print(f"Item {j+1}: {item_text}")
                print(f"Item {j+1} HTML: {item_html}")
                
                # Check if this item has a link
                invoice_link = await item.query_selector("a.a-link-normal")
                if invoice_link:
                    link_text = await page.evaluate("el => el.textContent.trim()", invoice_link)
                    link_href = await invoice_link.get_attribute("href")
                    print(f"  Link text: {link_text}")
                    print(f"  Link URL: {link_href}")
            
            # Wait longer for user to see the popover and interact with it manually if needed
            print("Pausing for 30 seconds to let you see and interact with the popover...")
            print("You can manually click on items in the popover during this time")
            await asyncio.sleep(30)
            
            # Don't auto-close the popover to allow manual interaction
            print("Popover remains open for further manual interaction")
            
        except Exception as e:
            print(f"Error while handling popover: {e}")
            await page.screenshot(path=f"error_state_{order_id}.png")
            print(f"Saved error state screenshot to error_state_{order_id}.png")
            
    except Exception as e:
        print(f"Error processing order {order_id}: {e}")
        await page.screenshot(path="error_screenshot.png")
        print("Saved error screenshot to error_screenshot.png")
    
    print("\nFinished invoice popover exploration")

async def browser_download_pdf(page, url, target_path):
    """
    Download a PDF using the browser's fetch API to maintain authentication.
    
    Args:
        page: The browser page object with an active authenticated session
        url: The URL of the PDF to download
        target_path: The file path where the PDF should be saved
    
    Returns:
        Boolean indicating success or failure
    """
    print(f"\n--- DOWNLOADING PDF USING BROWSER FETCH ---")
    print(f"URL: {url}")
    print(f"Target save path: {target_path}")
    
    try:
        # Create the target directory if it doesn't exist
        parent_dir = os.path.dirname(target_path)
        os.makedirs(parent_dir, exist_ok=True)
        
        # Take a screenshot of the current page for reference
        await page.screenshot(path=f"before_download_{os.path.basename(target_path)}.png")
        
        # Use the browser's fetch API to download the file
        # This keeps all session cookies and headers intact
        pdf_data = await safe_evaluate(page, """async (url) => {
            try {
                const response = await fetch(url, {
                    method: 'GET',
                    credentials: 'include',
                    redirect: 'follow'
                });
                
                if (!response.ok) {
                    return { 
                        success: false, 
                        error: `HTTP error ${response.status}: ${response.statusText}`,
                        status: response.status
                    };
                }
                
                // Get the response as array buffer
                const buffer = await response.arrayBuffer();
                
                // Convert ArrayBuffer to Base64
                const binary = new Uint8Array(buffer);
                let base64 = '';
                const len = binary.byteLength;
                for (let i = 0; i < len; i++) {
                    base64 += String.fromCharCode(binary[i]);
                }
                
                return { 
                    success: true, 
                    data: btoa(base64),
                    contentType: response.headers.get('content-type') || 'application/octet-stream'
                };
            } catch (error) {
                return { success: false, error: error.toString() };
            }
        }""", url)
        
        if not pdf_data.get('success'):
            print(f"Failed to fetch PDF: {pdf_data.get('error')}")
            print(f"Status code: {pdf_data.get('status')}")
            return False
        
        # Decode base64 data
        import base64
        binary_data = base64.b64decode(pdf_data['data'])
        
        # Write the binary data to the target file
        with open(target_path, 'wb') as f:
            f.write(binary_data)
            
        # Check if file was saved successfully
        if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
            file_size = os.path.getsize(target_path)
            print(f"Successfully downloaded PDF to {target_path} ({file_size} bytes)")
            
            # Check if the file starts with PDF signature (%PDF)
            with open(target_path, 'rb') as f:
                header = f.read(5)
                if header.startswith(b'%PDF'):
                    print("File is a valid PDF (has correct PDF header)")
                else:
                    print("Warning: File does not begin with PDF signature - may be corrupted")
                    # Save the first few bytes for debugging
                    print(f"File header: {header}")
            
            return True
        else:
            print(f"File not created or empty after download attempt")
            return False
            
    except Exception as e:
        print(f"Error downloading PDF with browser fetch: {e}")
        
        # Try a fallback approach - direct redirection capture
        try:
            print("Trying fallback approach - capturing redirection...")
            
            # Create a function to intercept requests
            async def on_request(request):
                if request.resource_type == "document" and "pdf" in request.url.lower():
                    print(f"Intercepted PDF request: {request.url}")
                    
                    # Get the complete request headers
                    headers = request.headers
                    print(f"Request headers: {headers}")
                    
                    # Create a new fetch request with the same headers
                    import requests
                    try:
                        cookies = await page.context.cookies()
                        cookies_dict = {cookie['name']: cookie['value'] for cookie in cookies}
                        
                        response = requests.get(
                            request.url,
                            headers=headers,
                            cookies=cookies_dict,
                            verify=False,
                            allow_redirects=True,
                            timeout=30
                        )
                        
                        if response.status_code == 200:
                            with open(target_path, 'wb') as f:
                                f.write(response.content)
                            print(f"Fallback downloaded {len(response.content)} bytes")
                            return True
                    except Exception as req_err:
                        print(f"Fallback request failed: {req_err}")
            
            # Create a new page and listen for requests
            context = page.context
            fallback_page = await context.new_page()
            fallback_page.on("request", on_request)
            
            # Navigate to the URL
            await fallback_page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)  # Wait for any redirects
            await fallback_page.close()
            
            # Check if file exists and is valid
            if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
                print(f"Fallback method successfully downloaded file ({os.path.getsize(target_path)} bytes)")
                return True
                
            return False
            
        except Exception as alt_e:
            print(f"Fallback approach failed: {alt_e}")
            return False

class DownloadTracker:
    """Track which invoices have been downloaded to avoid duplicates"""
    def __init__(self):
        self.log_file = "downloaded_invoices.json"
        self.downloaded = self._load_log()
        self.session_downloads = set()  # Track this session's downloads
        
    def _load_log(self):
        try:
            with open(self.log_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def is_downloaded(self, order_id, invoice_id):
        """Check if this invoice was already downloaded"""
        key = f"{order_id}:{invoice_id}"
        return key in self.downloaded
    
    def is_duplicate_path(self, path):
        """Check if we've already downloaded to this path in this session"""
        return str(path) in self.session_downloads
        
    def mark_downloaded(self, order_id, invoice_id, path):
        """Record a successful download"""
        key = f"{order_id}:{invoice_id}"
        self.downloaded[key] = {
            "path": str(path),
            "timestamp": datetime.now().isoformat()
        }
        self.session_downloads.add(str(path))
        self._save_log()
        
    def _save_log(self):
        with open(self.log_file, 'w') as f:
            json.dump(self.downloaded, f, indent=2)

# Create a global instance
download_tracker = DownloadTracker()

async def process_invoice_popover(page, context, order_id, order_date, month_year_folders):
    """Process the invoice popover and download invoices directly."""
    # Find the target folder for this order
    month_year = get_month_year_from_date(order_date)
    target_folder = month_year_folders.get(month_year, Path("Amazon"))
    print(f"Target folder for order {order_id} (date: {order_date}): {target_folder}")
    
    # Create the folder if it doesn't exist
    if not target_folder.exists():
        target_folder.mkdir(parents=True, exist_ok=True)
        print(f"Created directory: {target_folder}")
    
    # Wait for the popover to appear
    print("Waiting for invoice popover menu...")
    popover_selector = "div.a-popover-wrapper"
    await page.wait_for_selector(popover_selector, timeout=10000)
    print("Invoice popover appeared")
    
    # Take a screenshot to see the popover
    await page.screenshot(path=f"invoice_popover_{order_id}.png")
    
    # Get the popover
    popover = await page.query_selector(popover_selector)
    if not popover:
        print("Could not find popover")
        return 0
    
    # Find all invoice links in the popover
    invoice_links = await popover.query_selector_all("a.a-link-normal")
    print(f"Found {len(invoice_links)} links in the popover")
    
    # Track downloads
    downloaded_count = 0
    
    # Process each link
    for i, link in enumerate(invoice_links):
        try:
            link_text = await page.evaluate("el => el.textContent.trim()", link)
            link_href = await link.get_attribute("href")
            
            print(f"Link {i+1}: {link_text}")
            print(f"URL: {link_href}")
            
            # Skip if not an invoice link
            if not ("Invoice" in link_text or "Credit note" in link_text or "Factuur" in link_text):
                print(f"Skipping non-invoice link: {link_text}")
                continue
            
            # Create target filename
            clean_link_text = link_text.replace(" ", "_").replace("/", "-").lower()
            target_filename = f"{order_id}_{clean_link_text}_{i+1}.pdf"
            target_path = target_folder / target_filename
            
            print(f"Will download to: {target_path}")
            
            # Use wget to download directly (bypassing JavaScript and browser issues)
            success = await download_pdf(context, link_href, str(target_path))
            if success:
                downloaded_count += 1
                print(f"Successfully downloaded invoice {i+1}")
            else:
                print(f"Failed to download invoice {i+1}")
                
            # Wait briefly between downloads
            await asyncio.sleep(1)
            
        except Exception as e:
            print(f"Error processing link {i+1}: {e}")
    
    print(f"Downloaded {downloaded_count} invoices for order {order_id}")
    return downloaded_count

async def close_popover(page):
    """
    Close any open popovers by clicking outside or on the close button.
    
    Args:
        page: The browser page object
    """
    try:
        # First try to click the close button if it exists
        close_button = await page.query_selector("button.a-button-close")
        if close_button:
            print("Found close button, clicking it...")
            await close_button.click()
            await asyncio.sleep(1)  # Wait for popover to close
            return
            
        # If no close button or clicking it failed, click outside the popover
        print("Clicking outside the popover to close it...")
        # Click in the top-left corner of the page (usually outside any popover)
        await page.mouse.click(10, 10)
        await asyncio.sleep(1)  # Wait for popover to close
        
        # Verify the popover is closed
        popover = await page.query_selector("div.a-popover-wrapper:visible")
        if popover:
            print("Popover still visible after clicking outside, pressing ESC key...")
            # Try pressing ESC key
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)  # Wait for popover to close
    except Exception as e:
        print(f"Error closing popover: {e}")

async def navigate_to_next_page(page):
    """
    Navigate to the next page of orders if pagination exists.
    
    Args:
        page: The browser page object
        
    Returns:
        Boolean indicating whether navigation to next page was successful
    """
    print("\n--- NAVIGATING TO NEXT PAGE OF ORDERS ---\n")
    
    try:
        # Save current URL for debugging
        current_url = page.url
        print(f"Current URL before navigation: {current_url}")
        
        # Take a screenshot to see the pagination area
        await page.screenshot(path="pagination_before.png")
        
        # Check if pagination exists
        pagination = await page.query_selector("ul.a-pagination")
        if not pagination:
            print("No pagination found on the page")
            return False
        
        # Find the "Next" button
        next_button = await pagination.query_selector("li.a-last a")  # Look for the anchor inside the li
        
        if not next_button:
            next_button = await pagination.query_selector("li.a-last")  # Try just the li element
            
            if not next_button:
                print("No 'Next' button found in pagination")
                return False
            
            # If we found the li but not the anchor, check if it has a child anchor
            next_link = await next_button.query_selector("a")
            if next_link:
                next_button = next_link  # Use the anchor for clicking
            else:
                print("'Next' button doesn't have a clickable link")
                return False
        
        # Check if the "Next" button is disabled
        parent_li = await next_button.get_property("parentElement")
        parent_class = await parent_li.get_attribute("class") if parent_li else None
        
        if parent_class and "a-disabled" in parent_class:
            print("'Next' button is disabled - reached the last page")
            return False
        
        # Get the href attribute (crucial for proper navigation)
        next_href = await next_button.get_attribute("href")
        print(f"Next button href: {next_href}")
        
        if not next_href:
            print("No href attribute found on Next button")
            return False
        
        # Store identifiers for the current page's orders to detect changes
        print("Capturing identifiers of current orders...")
        before_orders = await page.query_selector_all(".a-box-group")
        
        # Extract order IDs to compare before and after navigation
        before_order_ids = []
        for box in before_orders[:3]:  # Just check the first few orders
            try:
                order_id_container = await box.query_selector(".yohtmlc-order-id")
                if order_id_container:
                    raw_text = await page.evaluate("el => el.textContent.trim()", order_id_container)
                    before_order_ids.append(raw_text)
            except Exception:
                pass
        
        print(f"Current page has these order IDs: {before_order_ids}")
        
        # Extract pagination current page indicator
        current_page_indicator = await pagination.query_selector("li.a-selected")
        current_page_num = None
        if current_page_indicator:
            current_page_text = await page.evaluate("el => el.textContent.trim()", current_page_indicator)
            print(f"Current pagination indicator: {current_page_text}")
            try:
                current_page_num = int(current_page_text)
            except ValueError:
                pass
        
        # We'll now navigate using the direct href rather than just clicking
        # This is more reliable as it uses the full navigation path
        absolute_url = next_href
        if next_href.startswith('/'):
            # Extract the base domain
            base_domain = re.match(r'(https?://[^/]+)', current_url).group(1)
            absolute_url = base_domain + next_href
        
        print(f"Navigating directly to: {absolute_url}")
        
        # Navigate directly to the next page URL
        await page.goto(absolute_url, timeout=60000)
        
        # Wait for the page to load completely
        await page.wait_for_load_state("networkidle", timeout=60000)
        await asyncio.sleep(3)  # Extra delay for stability
        
        # Take a screenshot after navigation
        await page.screenshot(path="pagination_after.png")
        
        # Check if we're still on the orders page
        new_url = page.url
        print(f"URL after navigation: {new_url}")
        
        if not ("your-orders" in new_url or "order-history" in new_url):
            print("Not on orders page after navigation!")
            return False
            
        # Verify we've moved to a new page by checking order IDs
        after_orders = await page.query_selector_all(".a-box-group")
        
        # Extract order IDs from new page
        after_order_ids = []
        for box in after_orders[:3]:  # Check first few orders
            try:
                order_id_container = await box.query_selector(".yohtmlc-order-id")
                if order_id_container:
                    raw_text = await page.evaluate("el => el.textContent.trim()", order_id_container)
                    after_order_ids.append(raw_text)
            except Exception:
                pass
                
        print(f"New page has these order IDs: {after_order_ids}")
        
        # Check if order IDs are different
        if before_order_ids and after_order_ids and before_order_ids == after_order_ids:
            print("Warning: Order IDs are the same on both pages - may not have navigated properly")
            
            # Check pagination indicator on new page
            new_page_indicator = await pagination.query_selector("li.a-selected")
            if new_page_indicator:
                new_page_text = await page.evaluate("el => el.textContent.trim()", new_page_indicator)
                print(f"New pagination indicator: {new_page_text}")
                
                try:
                    new_page_num = int(new_page_text)
                    if current_page_num and new_page_num > current_page_num:
                        print(f"Pagination indicator changed from {current_page_num} to {new_page_num}")
                        return True
                except ValueError:
                    pass
                    
            print("Navigation seems to have failed - couldn't verify new page")
            return False
            
        else:
            print("Order IDs differ - successfully navigated to a new page")
            return True
            
    except Exception as e:
        print(f"Error navigating to next page: {e}")
        # Take a screenshot of the error state
        await page.screenshot(path="pagination_error.png")
        print("Saved error state screenshot to pagination_error.png")
        return False

async def main():
    """Main entry point for the script."""
    try:
        page, context = await manual_login()
        
        if page and context:
            print("Login complete - now processing orders page by page")
            
            # Track total statistics
            total_orders_processed = 0
            total_invoices_downloaded = 0
            page_number = 1
            
            # Process pages until there are no more
            while True:
                print(f"\n{'='*60}")
                print(f"PROCESSING PAGE {page_number} OF ORDERS")
                print(f"{'='*60}")
                
                # Extract order details from the current page
                print(f"Extracting order details from page {page_number}...")
                orders_data = await extract_order_details(page)
                
                if orders_data:
                    # Count orders on this page
                    page_order_count = len(orders_data)
                    total_orders_processed += page_order_count
                    print(f"Found {page_order_count} valid orders on page {page_number}")
                    
                    # Create folder structure for the extracted orders
                    month_year_folders = create_folder_structure(orders_data)
                    print(f"Created folder structure for orders on page {page_number}")
                    
                    # Download invoices for this page
                    page_downloads = await download_invoices(page, context, orders_data, month_year_folders)
                    total_invoices_downloaded += page_downloads
                    
                    print(f"Page {page_number} complete: Downloaded {page_downloads} invoices from {page_order_count} orders")
                    print(f"Running totals: {total_orders_processed} orders processed, {total_invoices_downloaded} invoices downloaded")
                else:
                    print(f"No valid orders found on page {page_number}")
                
                # Try to navigate to the next page
                print(f"\nChecking for additional pages of orders...")
                has_next_page = await navigate_to_next_page(page)
                
                if not has_next_page:
                    print(f"No more pages available. Finished processing {page_number} page(s) of orders.")
                    break
                
                # If we reached here, pagination succeeded - increment page counter
                page_number += 1
                print(f"Moving to page {page_number}...")
                
                # Small delay before processing the next page
                await asyncio.sleep(3)
            
            # Final summary
            print("\n" + "="*60)
            print("DOWNLOAD SUMMARY")
            print("="*60)
            print(f"Total pages processed: {page_number}")
            print(f"Total orders processed: {total_orders_processed}")
            print(f"Total invoices downloaded: {total_invoices_downloaded}")
            
            if total_invoices_downloaded == 0:
                print("\nNo invoices were automatically downloaded.")
                print("Please download invoices manually from the Amazon Orders page.")
                print("Save them in the appropriate month-year folders that have been created.")
            
            # Keep the browser open for a while to allow manual interaction
            print("\nBrowser will remain open for 2 more minutes for further manual interaction.")
            print("You can manually download any remaining invoices during this time.")
            await asyncio.sleep(120)
            
            # Close the browser
            await context.close()
    
    except (RuntimeError, ValueError, TimeoutError) as e:
        print(f"An error occurred: {e}")
    finally:
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())