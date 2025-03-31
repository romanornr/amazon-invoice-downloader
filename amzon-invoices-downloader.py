#!/usr/bin/env python3
import os
import asyncio
import sys
import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

async def main():
	# Load environment variables from .env file
	load_dotenv()
	
	# Get email from environment variables
	email = os.getenv('AMAZON_EMAIL')
	
	if not email:
		print("Error: AMAZON_EMAIL environment variable not set.")
		print("Please set this in your .env file or as environment variables.")
		return
	
	# Create Amazon folder if it doesn't exist
	amazon_folder = "Amazon"
	if not os.path.exists(amazon_folder):
		os.makedirs(amazon_folder)
		print(f"Created folder: {amazon_folder}")
	else:
		print(f"Using existing folder: {amazon_folder}")
	
	async with async_playwright() as p:
		# Launch the browser
		browser = await p.chromium.launch(headless=False)
		
		# Create a new context with download permissions
		context = await browser.new_context(
			accept_downloads=True
		)
		
		# Create a new page
		page = await context.new_page()
		
		try:
			# Navigate directly to Amazon Orders page in English
			print("Navigating to Amazon Orders page...")
			
			# Increase timeout and handle navigation more robustly
			try:
				# First navigate to the main site with a shorter timeout
				await page.goto("https://www.amazon.nl/", timeout=60000)
				print("Loaded Amazon homepage")
				
				# Now try to navigate to the orders page
				await page.goto("https://www.amazon.nl/your-orders/orders", timeout=60000)
			except PlaywrightTimeoutError:
				print("Initial navigation timed out, but we'll continue with login")
			
			# Wait for the sign-in page to load
			print("Waiting for sign-in page...")
			try:
				await page.wait_for_selector("#ap_email", timeout=20000)
				print("On sign-in page - filling email...")
				
				# Fill in the email field
				await page.fill("#ap_email", email)
				
				# Click continue
				await page.click("#continue")
				
				print("Please enter your password manually in the browser window.")
				print("The browser will remain open for you to complete the login process.")
			except PlaywrightTimeoutError:
				print("Could not find email field. You may need to log in manually.")
				print("Please complete the login process in the browser window.")
			
			# Wait for user to manually enter password and complete login
			print("Waiting for login to complete...")
			
			# Take a more robust approach to detect when we're logged in
			logged_in = False
			for _ in range(60):  # Wait up to 5 minutes
				await asyncio.sleep(5)
				
				# Check for logged-in state by looking for the sign-in button
				try:
					sign_in_button = await page.query_selector("#nav-link-accountList")
					if sign_in_button:
						print("Detected that we're logged in!")
						logged_in = True
						break
				except Exception:
					pass
				
				# Also check if we're on the orders page
				current_url = page.url
				print(f"Current URL: {current_url}")
				if "your-orders" in current_url or "order-history" in current_url:
					print("Successfully reached the orders page!")
					logged_in = True
					break
			
			if not logged_in:
				print("Could not verify successful login. May need to restart.")
				return
			
			# Make sure we're on the orders page
			print("Navigating to Orders page...")
			try:
				# Try to navigate to the orders page with a longer timeout
				await page.goto("https://www.amazon.nl/your-orders/orders", timeout=60000)
				await page.wait_for_load_state("networkidle", timeout=60000)
				print("Orders page loaded")
			except PlaywrightTimeoutError:
				print("Timeout while loading orders page, but continuing anyway")
				# Take a screenshot to see what page we're on
				await page.screenshot(path=os.path.join(amazon_folder, "orders_page_timeout.png"))
				print(f"Saved screenshot to {amazon_folder}/orders_page_timeout.png")
			
			# Now let's download invoices
			print("Beginning to download invoices...")
			
			# Take a screenshot for diagnostics
			await page.screenshot(path=os.path.join(amazon_folder, "amazon_logged_in.png"))
			print(f"Saved screenshot to {amazon_folder}/amazon_logged_in.png")
			
			# Process invoices directly from the orders page
			await download_invoices(context, page, amazon_folder)
			
			print("Invoice download process completed!")
			print("You can now interact with the page manually.")
			
			# Keep browser open for manual interaction
			input("Press Enter to close the browser when you're done...")
			
		except Exception as e:
			print(f"Error during process: {e}")
			await page.screenshot(path=os.path.join(amazon_folder, "error_screenshot.png"))
			print(f"Saved error screenshot to {amazon_folder}/error_screenshot.png")
			
		finally:
			# Close the browser
			await browser.close()

async def download_invoices(context, page, amazon_folder):
	"""Download all available invoices from the orders page."""
	
	print("Analyzing page structure to find invoices...")
	
	# Wait for page to be fully loaded with increased timeout
	try:
		await page.wait_for_load_state("networkidle", timeout=30000)
	except PlaywrightTimeoutError:
		print("Timeout waiting for page to load, continuing anyway")
	
	# Take a screenshot for debugging
	await page.screenshot(path=os.path.join(amazon_folder, "amazon_orders_page.png"))
	print(f"Saved screenshot to {amazon_folder}/amazon_orders_page.png for debugging")
	
	# Get the page HTML for debugging
	html_content = await page.content()
	with open(os.path.join(amazon_folder, "amazon_orders_page.html"), "w", encoding="utf-8") as f:
		f.write(html_content)
	print(f"Saved page HTML to {amazon_folder}/amazon_orders_page.html for analysis")
	
	# Looking specifically for invoice popovers
	print("Looking for invoice popovers...")
	
	# Find all invoice buttons (these open popovers)
	popover_selector = "span.a-declarative[data-action='a-popover']"
	popover_elements = await page.query_selector_all(popover_selector)
	print(f"Found {len(popover_elements)} popover elements")
	
	# Track how many invoices were downloaded
	total_invoices_downloaded = 0
	
	# Process each popover that might contain an invoice
	for i, popover in enumerate(popover_elements):
		try:
			# Skip Prime Video orders
			has_prime_video = await popover.evaluate('''(element) => {
				// Navigate up to the order row
				let orderRow = element;
				while (orderRow && !orderRow.classList.contains('a-box-group')) {
					orderRow = orderRow.parentElement;
				}
				
				// Check if it's a Prime Video order
				if (orderRow) {
					const primeVideoSpan = orderRow.querySelector("span.a-size-small.a-color-secondary.a-text-bold");
					return primeVideoSpan && primeVideoSpan.textContent.includes("Prime Video");
				}
				return false;
			}''')
			
			if has_prime_video:
				print(f"⏭️  Skipping Prime Video order {i+1}")
				continue
				
			# Check if this popover has an invoice link
			invoice_link = await popover.query_selector("a:has-text('Invoice'), a:has-text('Factuur')")
			if not invoice_link:
				continue
			
			print(f"Found invoice popover {i+1}")
			
			# Get the order ID if possible
			order_id = f"order_{i+1}"  # Default order ID if not found
			try:
				# Try to get the order ID from the data attribute or nearby elements
				order_id_attr = await popover.get_attribute("data-a-popover")
				if order_id_attr and "orderId" in order_id_attr:
					import re
					order_id_match = re.search(r'orderId=([A-Z0-9-]+)', order_id_attr)
					if order_id_match:
						order_id = order_id_match.group(1)
			except Exception as e:
				print(f"Could not extract order ID: {e}")
			
			# Click the invoice link to open the popover
			print(f"Clicking invoice link for order {order_id}...")
			await invoice_link.click()
			await page.wait_for_timeout(1000)  # Wait for popover to appear
			
			# Now look for PDF links in the popover
			print("Looking for direct PDF links in popover...")
			# The popover should now be visible
			await page.screenshot(path=os.path.join(amazon_folder, f"popover_{order_id}.png"))
			
			# Save the HTML of the popover for debugging
			popover_html = await page.evaluate('''() => {
				const popover = document.querySelector(".a-popover-content");
				return popover ? popover.outerHTML : "No popover found";
			}''')
			with open(os.path.join(amazon_folder, f"popover_{order_id}.html"), "w", encoding="utf-8") as f:
				f.write(popover_html)
			
			# Look for S3 PDF links which are direct download links
			pdf_links = await page.query_selector_all(".a-popover-content a[href*='s3.amazonaws.com'], .a-popover-content a[href*='.pdf']")
			if len(pdf_links) > 0:
				print(f"Found {len(pdf_links)} direct S3 PDF links in popover")
			else:
				# Look for other potential invoice links if no direct PDF links
				pdf_links = await page.query_selector_all(".a-popover-content a:has-text('Invoice'), .a-popover-content a:has-text('Credit note')")
				print(f"Found {len(pdf_links)} potential invoice links in popover")
			
			# Function to handle saving PDFs directly from the browser
			async def save_pdf_from_page(browser_page, filename):
				try:
					# Use JavaScript to fetch the PDF content directly
					pdf_data = await browser_page.evaluate('''async () => {
						const response = await fetch(document.location.href);
						const buffer = await response.arrayBuffer();
						return Array.from(new Uint8Array(buffer));
					}''')
					
					# Convert the array back to bytes and save to a file
					pdf_bytes = bytes(pdf_data)
					
					# Ensure it's a PDF by checking the magic number
					if pdf_bytes.startswith(b'%PDF'):
						with open(filename, 'wb') as f:
							f.write(pdf_bytes)
						print(f"✅ Successfully saved PDF to {filename}")
						return True
					else:
						print(f"❌ Content doesn't appear to be a valid PDF for {filename}")
						return False
				except Exception as e:
					print(f"❌ Error saving PDF content: {e} for {filename}")
					return False
			
			# Download each PDF
			for pdf_idx, pdf_link in enumerate(pdf_links):
				try:
					# Get the link URL
					pdf_url = await pdf_link.get_attribute("href")
					link_text = await pdf_link.text_content()
					
					print(f"Processing PDF link {pdf_idx+1}: {link_text.strip()}")
					print(f"PDF URL: {pdf_url}")
					
					# Try to get the order date from nearby elements
					order_date = datetime.datetime.now().strftime("%m-%y")  # Default to current month-year
					try:
						# Look for date information near the order
						order_row = await popover.evaluate('''(element) => {
							// Navigate up to the order row
							let orderRow = element;
							while (orderRow && !orderRow.classList.contains('a-box-group')) {
								orderRow = orderRow.parentElement;
							}
							return orderRow ? orderRow.textContent : "";
						}''')
						
						# Try to extract a date from the order text
						import re
						date_patterns = [
							r'(\d{1,2})[\s/-](\d{1,2})[\s/-](\d{2,4})',  # Various date formats
							r'(\w+)\s+(\d{1,2}),?\s+(\d{4})'  # Jan 15, 2023 format
						]
						
						for pattern in date_patterns:
							date_match = re.search(pattern, order_row)
							if date_match:
								# Try to parse the date
								try:
									if len(date_match.groups()) == 3:
										if date_match.group(1).isdigit():
											# Numeric date format
											month = int(date_match.group(1))
											year = date_match.group(3)
											if len(year) == 2:
												year = f"20{year}"
											order_date = f"{month:02d}-{year[2:4]}"
										else:
											# Month name format
											month_names = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, 
														"jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
											month_str = date_match.group(1).lower()[:3]
											if month_str in month_names:
												month = month_names[month_str]
												year = date_match.group(3)
												order_date = f"{month:02d}-{year[2:4]}"
									break
								except Exception as e:
									print(f"Error parsing date: {e}")
					except Exception as e:
						print(f"Error extracting order date: {e}")
					
					file_path = os.path.join(amazon_folder, f"{order_date}_amazon_invoice_{order_id}_{pdf_idx+1}.pdf")
					
					# Check if this is a direct S3 PDF link
					if pdf_url and "s3.amazonaws.com" in pdf_url.lower() and "pdf" in pdf_url.lower():
						print("Direct S3 PDF link detected, downloading...")
						
						# Create a new page to download the PDF
						pdf_page = await context.new_page()
						try:
							await pdf_page.goto(pdf_url, timeout=30000)
							print("PDF page loaded, attempting to save content...")
							
							# Save the PDF content directly
							if await save_pdf_from_page(pdf_page, file_path):
								total_invoices_downloaded += 1
								
						except Exception as e:
							print(f"Error navigating to PDF URL: {e}")
						finally:
							await pdf_page.close()
					else:
						# Try clicking the link, which may open in a new tab or in a popup
						print("Regular invoice link, trying various methods...")
						
						# First try: open in the same tab with Ctrl key to force new tab
						async with context.expect_page(timeout=15000) as new_page_info:
							await pdf_link.click(button="middle")  # Middle click to open in new tab
						
						invoice_page = await new_page_info.value
						print(f"Opened invoice in new tab: {invoice_page.url}")
						
						try:
							# Wait for the page to load
							await invoice_page.wait_for_load_state("networkidle", timeout=30000)
							await invoice_page.screenshot(path=os.path.join(amazon_folder, f"invoice_page_{order_id}_{pdf_idx}.png"))
							
							# Check if this appears to be a PDF page
							if "pdf" in invoice_page.url.lower() or await invoice_page.evaluate('''() => {
								const contentType = document.contentType || '';
								return contentType.includes('pdf');
							}'''):
								print("This appears to be a PDF page")
								
								# Try to save the PDF directly from the page
								if await save_pdf_from_page(invoice_page, file_path):
									total_invoices_downloaded += 1
							else:
								# Look for download buttons on the page
								download_button = await invoice_page.query_selector("a:has-text('Download'), button:has-text('Download')")
								if download_button:
									print("Found download button on page")
									try:
										async with invoice_page.expect_download(timeout=15000) as download_info:
											await download_button.click()
										
										download = await download_info.value
										await download.save_as(file_path)
										print(f"✅ Successfully downloaded invoice to {file_path}")
										total_invoices_downloaded += 1
									except PlaywrightTimeoutError:
										print("Timeout waiting for download, trying direct save...")
										# Try to save the page content directly
										if await save_pdf_from_page(invoice_page, file_path):
											total_invoices_downloaded += 1
								else:
									print("No download button found on page")
									print("Trying to save page content as PDF...")
									# Try to save the page content directly
									if await save_pdf_from_page(invoice_page, file_path):
										total_invoices_downloaded += 1
									else:
										print(f"❌ Failed to save PDF from this page")
							
						except Exception as e:
							print(f"Error processing invoice page: {e}")
						finally:
							# Close the invoice page
							await invoice_page.close()
				
				except Exception as e:
					print(f"Error processing PDF link {pdf_idx+1}: {e}")
			
			# Close the popover when done
			await page.keyboard.press("Escape")
			await page.wait_for_timeout(1000)
			
		except Exception as e:
			print(f"Error processing popover {i+1}: {e}")
	
	print(f"Total invoices processed on this page: {total_invoices_downloaded}")
	
	# Check if there are more pages of orders
	next_button = await page.query_selector("li.a-last > a")
	if next_button:
		print("Found more pages of orders. Navigating to next page...")
		await next_button.click()
		
		# Wait for the next page to load
		try:
			await page.wait_for_load_state("networkidle", timeout=30000)
		except PlaywrightTimeoutError:
			print("Timeout waiting for next page to load")
			await page.screenshot(path=os.path.join(amazon_folder, "next_page_timeout.png"))
		
		# Process the next page of orders recursively
		await download_invoices(context, page, amazon_folder)

if __name__ == '__main__':
	# Force stdout to flush after each print
	print = lambda *args, **kwargs: __builtins__.print(*args, **kwargs, flush=True)
	asyncio.run(main())

