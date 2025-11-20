#!/bin/bash

# Deployment script for Admin Dashboard
# Usage: ./deploy.sh [bucket-name] [distribution-id]

set -e

echo "🚀 Admin Dashboard Deployment Script"
echo "===================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running from correct directory
if [ ! -f "package.json" ]; then
    echo -e "${RED}❌ Error: package.json not found. Run this script from admin-dashboard directory${NC}"
    exit 1
fi

# Get bucket name and distribution ID
if [ -z "$1" ]; then
    echo -e "${YELLOW}⚠️  No bucket name provided. Attempting to get from CDK outputs...${NC}"
    BUCKET_NAME=$(aws cloudformation describe-stacks \
        --stack-name AdminStack \
        --query "Stacks[0].Outputs[?contains(OutputKey,'Bucket')].OutputValue" \
        --output text 2>/dev/null || echo "")
    
    if [ -z "$BUCKET_NAME" ]; then
        echo -e "${RED}❌ Error: Could not get bucket name. Please provide as argument:${NC}"
        echo "   ./deploy.sh <bucket-name> <distribution-id>"
        exit 1
    fi
else
    BUCKET_NAME=$1
fi

if [ -z "$2" ]; then
    echo -e "${YELLOW}⚠️  No distribution ID provided. Attempting to get from CDK outputs...${NC}"
    DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
        --stack-name AdminStack \
        --query "Stacks[0].Outputs[?contains(OutputKey,'Distribution')].OutputValue" \
        --output text 2>/dev/null || echo "")
    
    if [ -z "$DISTRIBUTION_ID" ]; then
        echo -e "${YELLOW}⚠️  Warning: Could not get distribution ID. Skipping cache invalidation.${NC}"
    fi
else
    DISTRIBUTION_ID=$2
fi

echo ""
echo -e "${GREEN}📦 Bucket:${NC} $BUCKET_NAME"
if [ ! -z "$DISTRIBUTION_ID" ]; then
    echo -e "${GREEN}☁️  Distribution:${NC} $DISTRIBUTION_ID"
fi
echo ""

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  Warning: .env file not found. Using .env.example...${NC}"
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${YELLOW}📝 Please update .env with your AWS configuration${NC}"
    fi
fi

# Install dependencies
echo -e "${GREEN}📥 Installing dependencies...${NC}"
npm ci

# Build
echo -e "${GREEN}🏗️  Building application...${NC}"
npm run build

if [ ! -d "dist" ]; then
    echo -e "${RED}❌ Error: dist/ directory not found. Build failed.${NC}"
    exit 1
fi

# Upload to S3
echo -e "${GREEN}☁️  Uploading to S3...${NC}"
aws s3 sync dist/ s3://$BUCKET_NAME/ --delete

# Invalidate CloudFront cache
if [ ! -z "$DISTRIBUTION_ID" ]; then
    echo -e "${GREEN}🔄 Invalidating CloudFront cache...${NC}"
    INVALIDATION_ID=$(aws cloudfront create-invalidation \
        --distribution-id $DISTRIBUTION_ID \
        --paths "/*" \
        --query 'Invalidation.Id' \
        --output text)
    
    echo -e "${GREEN}✅ Invalidation created:${NC} $INVALIDATION_ID"
    echo -e "${YELLOW}⏳ Cache invalidation in progress (takes 1-5 minutes)${NC}"
fi

echo ""
echo -e "${GREEN}✅ Deployment complete!${NC}"
echo ""
echo "🌐 Your dashboard should be available at:"
echo "   https://$BUCKET_NAME.s3.amazonaws.com/index.html"
if [ ! -z "$DISTRIBUTION_ID" ]; then
    CF_DOMAIN=$(aws cloudfront get-distribution \
        --id $DISTRIBUTION_ID \
        --query 'Distribution.DomainName' \
        --output text 2>/dev/null || echo "")
    if [ ! -z "$CF_DOMAIN" ]; then
        echo "   https://$CF_DOMAIN"
    fi
fi
echo ""
