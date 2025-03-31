# Amazon Invoice Downloader

This script automates the downloading of invoices from Amazon's order history page. It navigates through your order history, identifies invoices, and downloads them as PDFs to a local folder.

## Overview

This repository contains two scripts for downloading Amazon invoices:
- `amazon-invoices-downloader.py` - The recommended script that works reliably, though slower
- `amazon-invoices.py` - Unreliable first attempt that does not really work but has cool features I need to implement

The main script (`amazon-invoices-downloader.py`) now includes improvements such as:
- Duplicate detection to avoid downloading the same invoice multiple times
- Improved error handling and more comprehensive logging
- A hash-based system to verify file content uniqueness


## TODO List for amazon-invoice-downloader.py

[] Organization by Month/Year: Creates a more structured folder organization system that sorts invoices into folders by month-year (MM-YYYY format)

[] Order Details Extraction: improve comprehensive order details extraction (lines 155-283) to capture not just invoice links but also product titles and other order metadata.

[] Fallback Mechanisms: Implements multiple fallback approaches for downloading PDFs when primary methods fail, including browser fetch API techniques

[] Improve debugging

[] Interactive Final Phase: Keeps the browser open for manual interaction after the automated process completes, allowing users to manually download any invoices that the automation missed.

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
   - Skips "Request invoice" and "Order Summary" links

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
   - Avoids duplicates by checking file content hashes

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

## Duplicate Prevention

The script now prevents downloading duplicate invoices by:
- Tracking all processed URLs to avoid re-downloading the same link
- Computing MD5 hashes of file content to detect duplicates even if URLs differ
- Skipping downloads when content matches previously downloaded files
- Providing a `find_duplicates.sh` script to check for duplicate files in the Amazon folder

## Installation and Setup

### Prerequisites
- Python 3.7 or higher
- pip (Python package installer)

### Automated Setup

Use the included installation script:
```bash
./install.sh
```

This script will:
1. Check your Python version
2. Create a Python virtual environment
3. Install required dependencies
4. Install Playwright browsers
5. Create a sample `.env` file from the template

### Manual Setup

1. Clone this repository to your local machine

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

To run the recommended script:
```bash
python amazon-invoices-downloader.py
```

To run the faster but less reliable script:
```bash
python amazon-invoices.py
```

### Checking for Duplicates

After downloading invoices, you can check for duplicates:
```bash
./find_duplicates.sh
```

This will:
- Generate MD5 hashes for all downloaded PDF files
- Identify files with identical content
- Provide a summary of unique and duplicate files

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

## Legal Considerations

This script is designed for personal use to download your own invoices. Using it for scraping other users' data or excessive automation may violate Amazon's Terms of Service. Use responsibly and ethically.