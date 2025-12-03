#!/bin/bash

# S3 Sync Watch Mode - Auto sync dist folder to S3 and invalidate CloudFront
# Usage: ./watch-sync.sh

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration from CloudFormation
BUCKET_NAME="adminstack-adminfrontendbucket878574a2-fhkbssrz9cq2"
DISTRIBUTION_ID="E38R5G5I8DKMQE"
WATCH_DIR="dist"
REGION="ap-southeast-1"

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}  🔍 S3 Sync Watch Mode${NC}"
echo -e "${GREEN}================================${NC}"
echo "📦 Bucket: $BUCKET_NAME"
echo "☁️  Distribution: $DISTRIBUTION_ID"
echo "📁 Watch directory: $WATCH_DIR"
echo "🌏 Region: $REGION"
echo ""
echo -e "${YELLOW}⚡ Starting watch mode... Press Ctrl+C to stop${NC}"
echo ""

# Function to sync to S3 and invalidate CloudFront
sync_to_s3() {
    local timestamp=$(date '+%H:%M:%S')
    
    echo -e "${CYAN}[${timestamp}] 📤 Syncing to S3...${NC}"
    
    # Sync static assets with long cache
    aws s3 sync $WATCH_DIR/ s3://$BUCKET_NAME/ \
        --delete \
        --region $REGION \
        --cache-control "max-age=31536000,public" \
        --exclude "*.html" \
        --exclude "*.json" \
        --exclude "index.html"
    
    # Sync HTML/JSON without cache (để browser luôn lấy phiên bản mới)
    aws s3 sync $WATCH_DIR/ s3://$BUCKET_NAME/ \
        --delete \
        --region $REGION \
        --cache-control "no-cache,no-store,must-revalidate" \
        --exclude "*" \
        --include "*.html" \
        --include "*.json"
    
    echo -e "${CYAN}[${timestamp}] 🔄 Invalidating CloudFront cache...${NC}"
    INVALIDATION_ID=$(aws cloudfront create-invalidation \
        --distribution-id $DISTRIBUTION_ID \
        --paths "/*" \
        --query 'Invalidation.Id' \
        --output text 2>/dev/null)
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}[${timestamp}] ✅ Sync complete! Invalidation ID: ${INVALIDATION_ID}${NC}"
    else
        echo -e "${RED}[${timestamp}] ⚠️  Sync complete but CloudFront invalidation failed${NC}"
    fi
    
    echo -e "${GREEN}[${timestamp}] 🌐 Dashboard: https://d3soguz2qeegby.cloudfront.net${NC}"
    echo ""
}

# Check if dist folder exists
if [ ! -d "$WATCH_DIR" ]; then
    echo -e "${RED}❌ Error: $WATCH_DIR folder not found!${NC}"
    echo -e "${YELLOW}Run 'npm run build' first to create dist folder${NC}"
    exit 1
fi

# Initial sync
echo -e "${YELLOW}🚀 Performing initial sync...${NC}"
sync_to_s3

# Watch for changes
echo -e "${YELLOW} Watching for changes in $WATCH_DIR...${NC}"
echo ""

# Use inotifywait (Linux), fswatch (macOS), or fallback to hash-based watch
if command -v inotifywait &> /dev/null; then
    # Linux - inotifywait
    echo -e "${CYAN}Using inotifywait for file watching${NC}"
    while inotifywait -r -e modify,create,delete,move $WATCH_DIR 2>/dev/null; do
        sleep 1  # Debounce
        sync_to_s3
    done
elif command -v fswatch &> /dev/null; then
    # macOS - fswatch
    echo -e "${CYAN}Using fswatch for file watching${NC}"
    fswatch -o -r $WATCH_DIR | while read; do
        sleep 1  # Debounce
        sync_to_s3
    done
else
    # Fallback - hash-based watch (works on all platforms)
    echo -e "${YELLOW}Using hash-based file watching (install fswatch or inotifywait for better performance)${NC}"
    LAST_HASH=""
    while true; do
        if command -v md5sum &> /dev/null; then
            CURRENT_HASH=$(find $WATCH_DIR -type f -exec md5sum {} \; 2>/dev/null | sort | md5sum)
        else
            # Fallback for systems without md5sum
            CURRENT_HASH=$(find $WATCH_DIR -type f -exec stat -f "%m %N" {} \; 2>/dev/null | sort | md5)
        fi
        
        if [ "$CURRENT_HASH" != "$LAST_HASH" ] && [ -n "$CURRENT_HASH" ]; then
            LAST_HASH=$CURRENT_HASH
            sync_to_s3
        fi
        sleep 3
    done
fi
