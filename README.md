# Amazon Invoice Downloader

This script automates the downloading of invoices from Amazon's order history page. It navigates through your order history, identifies invoices, and downloads them as PDFs to a local folder.

There are 2 files:
- amazon-invoices.py
- amazon-invoices-downloader.py

In both I tried to scrape the invoices.
The amazon-invoices-downloader.py does work but it is very slow due to Amazon most likely security or ui quirks
amazon-invoices.py is very fast, can select which year to download etc. But it keeps downloading the first few invoices and the rest are copies

I am not sure if I can find loopholes. This whole script wouldn't be required if Amazon emailed us our invoices instead of marketing spam.

## How It Works

1. **Authentication**:
   - Uses Playwright to launch a Chromium browser in non-headless mode (visible UI)
   - Automates the initial login steps (entering email)
   - Requires manual password entry (security measure and to avoid Amazon's bot detection)
   - Waits for successful login by checking for the account menu or orders page URL

2. **Order Page Navigation**:
   - Navigates to the orders page
   - Takes screenshots for debugging
   - Saves HTML content for analysis

3. **Invoice Detection**:
   - Identifies invoice links within "popover" elements (Amazon's interactive UI components)
   - Extracts order IDs for proper file naming
   - Filters out non-invoice items (like Prime Video orders)

4. **PDF Extraction Methods**:
   - Uses multiple strategies to handle different invoice presentation methods:
     a) Direct S3 PDF links
     b) Invoice pages that open in new tabs
     c) Pages with download buttons
     d) PDF content embedded in HTML pages

5. **File Organization**:
   - Names files with order dates and IDs
   - Organizes downloads in an "Amazon" folder
   - Creates detailed logs with timestamps

## Anti-Scraping Measures and How We Bypass Them

Amazon employs several anti-scraping techniques. Here's how our script addresses them:

### 1. Login Detection
**Amazon's measure**: Uses sophisticated bot detection during login.  
**Our approach**: Semi-automated process with manual password entry to behave like a real user.

### 2. JavaScript-Based UI
**Amazon's measure**: Many elements are dynamically loaded with JavaScript.  
**Our approach**: Uses Playwright, a full browser automation tool that runs JavaScript like a real browser.

### 3. Short-Lived URLs
**Amazon's measure**: Pre-signed S3 URLs with short expiration times (often ~3 minutes).  
**Our approach**: Immediate navigation to and processing of URLs when detected.

### 4. Multiple Invoice Formats
**Amazon's measure**: Inconsistent presentation of invoices across different order types.  
**Our approach**: Multiple extraction methods to handle various scenarios:
   - JavaScript content extraction for embedded PDFs
   - New tab opening for invoice pages
   - Direct download handling

### 5. Client-Side Rendering
**Amazon's measure**: Placeholder URLs that get transformed client-side.  
**Our approach**: Uses browser-based clicks rather than trying to extract URLs directly. This ensures we trigger the JavaScript handlers that generate the actual download URLs.

### 6. Rate Limiting
**Amazon's measure**: Detection of rapid, automated interactions.  
**Our approach**: Adds strategic delays between operations to mimic human behavior.

## Error Handling and Logging

The script includes robust error handling:

- Comprehensive logging with timestamps and error categorization
- Screenshots at key points for debugging
- Popover HTML content saving for analysis
- Multiple fallback methods if primary PDF extraction fails

## Limitations

- Requires manual password entry
- May need adjustments as Amazon's site structure changes
- Cannot run headlessly (browser must be visible)
- May encounter temporary blocking if used excessively

## Usage Tips

1. Set the `AMAZON_EMAIL` environment variable before running
2. Be prepared to enter your password manually
3. Allow the script sufficient time to process orders
4. Don't use excessively to avoid triggering Amazon's anti-automation measures
5. Check the generated log file for detailed processing information

## Installation and Setup

### Prerequisites
- Python 3.7 or higher
- pip (Python package installer)

### Setup Instructions

1. Clone this repository to your local machine:

2. Create and activate a Python virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install required dependencies:
```bash
pip install playwright python-dotenv
```

4. Install Playwright browsers:
```bash
playwright install
```

5. Create a `.env` file with your Amazon email (or copy from the sample):
```bash
cp env-sample .env
```
Then edit the `.env` file to add your Amazon email.

### Running the Scripts

To run the faster script (which does not work and has issues):
```bash
python amazon-invoices.py
```

To run the slower but more reliable script:
```bash
python amazon-invoices-downloader.py
```

## Legal Considerations

This script is designed for personal use to download your own invoices. Using it for scraping other users' data or excessive automation may violate Amazon's Terms of Service. Use responsibly and ethically. 