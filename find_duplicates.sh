#!/bin/bash

# Directory to search for duplicates
AMAZON_DIR="./Amazon"
# Log file with date and time
LOG_FILE="duplicate_check_$(date +"%Y-%m-%d_%H-%M").log"

echo "Starting duplicate file check at $(date)" | tee -a "$LOG_FILE"
echo "Checking for duplicates in $AMAZON_DIR" | tee -a "$LOG_FILE"

# Find all PDF files and calculate their MD5 hashes
echo "Calculating MD5 hashes for all PDF files..." | tee -a "$LOG_FILE"
find "$AMAZON_DIR" -type f -name "*.pdf" | sort | xargs md5sum > "$AMAZON_DIR/hashes.txt"

# Find duplicate files based on their hashes
echo -e "\nFiles with identical content:" | tee -a "$LOG_FILE"
duplicate_found=false

awk '{print $1}' "$AMAZON_DIR/hashes.txt" | sort | uniq -d | while read hash; do
    echo -e "\nFiles with hash $hash:" | tee -a "$LOG_FILE"
    grep "$hash" "$AMAZON_DIR/hashes.txt" | awk '{print $2}' | tee -a "$LOG_FILE"
    duplicate_found=true
done

# Count total files and unique files
total_files=$(grep -c "\.pdf" "$AMAZON_DIR/hashes.txt")
unique_hashes=$(awk '{print $1}' "$AMAZON_DIR/hashes.txt" | sort | uniq | wc -l)

echo -e "\nSummary:" | tee -a "$LOG_FILE"
echo "Total PDF files: $total_files" | tee -a "$LOG_FILE"
echo "Unique content files: $unique_hashes" | tee -a "$LOG_FILE"
echo "Duplicate content files: $((total_files - unique_hashes))" | tee -a "$LOG_FILE"

if [ $((total_files - unique_hashes)) -eq 0 ]; then
    echo "No duplicate files found." | tee -a "$LOG_FILE"
fi

echo "Duplicate check completed at $(date)" | tee -a "$LOG_FILE"
echo "Results saved to $LOG_FILE"