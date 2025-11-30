#!/bin/bash
#
# Binance Historical Data Downloader
# Downloads klines from data.binance.vision
#
# Usage: ./download_binance_data.sh
#
# Data will be saved to: ./data/
#

set -e

DATA_DIR="./data"
SYMBOL="BTCUSDT"
BASE_URL="https://data.binance.vision/data/futures/um/monthly/klines"

# Create data directory
mkdir -p "$DATA_DIR"

# Intervals to download
INTERVALS=("5m" "15m" "1h" "4h" "1d" "1w")

# Date range: 2019-09 to 2025-11
START_YEAR=2019
START_MONTH=9
END_YEAR=2025
END_MONTH=11

echo "========================================"
echo "Binance Historical Data Downloader"
echo "Symbol: $SYMBOL"
echo "Source: data.binance.vision"
echo "========================================"

for INTERVAL in "${INTERVALS[@]}"; do
    echo ""
    echo "Downloading $INTERVAL data..."
    echo "----------------------------------------"

    OUTPUT_FILE="$DATA_DIR/${SYMBOL}_${INTERVAL}_futures.csv"
    TEMP_DIR="$DATA_DIR/temp_${INTERVAL}"
    mkdir -p "$TEMP_DIR"

    YEAR=$START_YEAR
    MONTH=$START_MONTH

    while [ "$YEAR" -lt "$END_YEAR" ] || ([ "$YEAR" -eq "$END_YEAR" ] && [ "$MONTH" -le "$END_MONTH" ]); do
        MONTH_STR=$(printf "%02d" $MONTH)
        FILENAME="${SYMBOL}-${INTERVAL}-${YEAR}-${MONTH_STR}.zip"
        URL="${BASE_URL}/${SYMBOL}/${INTERVAL}/${FILENAME}"

        echo -n "  Downloading ${YEAR}-${MONTH_STR}... "

        if wget -q --timeout=30 "$URL" -O "$TEMP_DIR/$FILENAME" 2>/dev/null; then
            # Extract CSV from ZIP
            unzip -q -o "$TEMP_DIR/$FILENAME" -d "$TEMP_DIR/" 2>/dev/null
            rm "$TEMP_DIR/$FILENAME"
            echo "OK"
        else
            echo "Not found"
        fi

        # Next month
        MONTH=$((MONTH + 1))
        if [ "$MONTH" -gt 12 ]; then
            MONTH=1
            YEAR=$((YEAR + 1))
        fi

        sleep 0.3
    done

    # Combine all CSV files
    echo "  Combining CSV files..."

    # Add header
    echo "open_time,open,high,low,close,volume,close_time,quote_volume,trades,taker_buy_volume,taker_buy_quote_volume,ignore" > "$OUTPUT_FILE"

    # Concatenate all CSVs (skip empty files)
    for f in "$TEMP_DIR"/*.csv; do
        if [ -f "$f" ]; then
            cat "$f" >> "$OUTPUT_FILE"
        fi
    done

    # Clean up
    rm -rf "$TEMP_DIR"

    # Count lines
    LINES=$(wc -l < "$OUTPUT_FILE")
    echo "  Saved: $OUTPUT_FILE ($((LINES - 1)) candles)"
done

echo ""
echo "========================================"
echo "Download Complete!"
echo "Data saved to: $DATA_DIR/"
echo "========================================"

# List downloaded files
echo ""
echo "Downloaded files:"
ls -lh "$DATA_DIR"/*.csv 2>/dev/null || echo "No CSV files found"
