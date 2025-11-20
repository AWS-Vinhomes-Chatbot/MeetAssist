# Deployment Guide for Admin Dashboard

## 📋 Prerequisites

1. **CDK Stack Deployed**: Ensure your CDK stack is fully deployed
2. **AWS CLI Configured**: `aws configure` with appropriate credentials
3. **Node.js 18+**: For building the React application

## 🔧 Step 1: Get CDK Outputs

After deploying the CDK stack, you'll get outputs like:

```bash
Outputs:
AdminStack.CognitoUserPoolId = us-east-1_XXXXXXXXX
AdminStack.CognitoAppClientId = XXXXXXXXXXXXXXXXXXX
AdminStack.AdminApiEndpoint = https://xxxxx.execute-api.us-east-1.amazonaws.com/prod
AdminStack.CloudFrontURL = https://dxxxxx.cloudfront.net
AdminStack.HistoryBucketName = adminstack-adminfrontendXXXXX
```

## 🔧 Step 2: Configure Environment

1. **Copy environment template:**
   ```bash
   cd admin-dashboard
   cp .env.example .env
   ```

2. **Update `.env` with CDK outputs:**
   ```env
   VITE_USER_POOL_ID=us-east-1_XXXXXXXXX
   VITE_USER_POOL_CLIENT_ID=XXXXXXXXXXXXXXXXXXX
   VITE_API_ENDPOINT=https://xxxxx.execute-api.us-east-1.amazonaws.com/prod
   VITE_COGNITO_DOMAIN=<your-cognito-domain>  # From Cognito Console
   VITE_REDIRECT_SIGN_IN=https://admin.meetassist.ai/
   VITE_REDIRECT_SIGN_OUT=https://admin.meetassist.ai/
   ```

3. **Get Cognito Domain:**
   - Go to AWS Console → Cognito → User Pools
   - Select your pool
   - Go to "App Integration" → "Domain"
   - If not set, create a domain (e.g., `bookingchatbotadmin`)
   - Domain will be: `bookingchatbotadmin.auth.us-east-1.amazoncognito.com`

## 🏗️ Step 3: Build Application

```bash
cd admin-dashboard

# Install dependencies
npm install

# Build for production
npm run build
```

This creates a `dist/` folder with optimized static files.

## 🚀 Step 4: Deploy to S3

### Option A: Using AWS CLI

```bash
# Get bucket name from CDK outputs
BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name AdminStack \
  --query "Stacks[0].Outputs[?OutputKey=='HistoryBucketName'].OutputValue" \
  --output text)

# Sync build files to S3
aws s3 sync dist/ s3://$BUCKET_NAME/ --delete

# Get CloudFront distribution ID
DISTRIBUTION_ID=$(aws cloudformation describe-stacks \
  --stack-name AdminStack \
  --query "Stacks[0].Outputs[?contains(OutputKey,'Distribution')].OutputValue" \
  --output text)

# Invalidate CloudFront cache
aws cloudfront create-invalidation \
  --distribution-id $DISTRIBUTION_ID \
  --paths "/*"
```

### Option B: Using CDK BucketDeployment (Automated)

The CDK stack already includes `BucketDeployment` construct. Simply:

```bash
# From project root
cdk deploy AdminStack

# This will automatically:
# 1. Build frontend (if configured)
# 2. Upload to S3
# 3. Invalidate CloudFront
```

## ✅ Step 5: Verify Deployment

1. **Access the dashboard:**
   - CloudFront URL: `https://dxxxxx.cloudfront.net`
   - Custom domain: `https://admin.meetassist.ai`

2. **Test login flow:**
   - Click "Login with Cognito"
   - Should redirect to Cognito Hosted UI
   - After login, should return to dashboard

3. **Check browser console:**
   - No 403/404 errors
   - No CORS errors
   - Authentication working

## 🔧 Step 6: Update Cognito Callback URLs (If needed)

If OAuth redirect fails:

```bash
# Update Cognito App Client callback URLs
aws cognito-idp update-user-pool-client \
  --user-pool-id <USER_POOL_ID> \
  --client-id <APP_CLIENT_ID> \
  --callback-urls "https://admin.meetassist.ai/","https://admin.meetassist.ai/callback" \
  --logout-urls "https://admin.meetassist.ai/","https://admin.meetassist.ai/logout"
```

## 🐛 Troubleshooting

### Issue: 403 Forbidden on assets
**Cause:** CloudFront OAI not properly configured  
**Solution:** Check S3 bucket policy allows OAI access

### Issue: OAuth redirect fails
**Cause:** Callback URLs mismatch  
**Solution:** Ensure exact match (including trailing slash) between:
- Cognito App Client callback URLs
- `VITE_REDIRECT_SIGN_IN` in `.env`

### Issue: API calls fail with CORS error
**Cause:** API Gateway CORS not configured  
**Solution:** Check AdminStack CORS configuration:
```python
default_cors_preflight_options=apigw.CorsOptions(
    allow_origins=["https://admin.meetassist.ai"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=True
)
```

### Issue: Blank page after login
**Cause:** CloudFront error responses not configured  
**Solution:** Check CloudFront distribution has error responses for 403/404 → 200

## 📝 Deployment Checklist

- [ ] CDK stack deployed successfully
- [ ] `.env` file configured with CDK outputs
- [ ] Cognito domain created
- [ ] Callback URLs match exactly
- [ ] Application built (`npm run build`)
- [ ] Files uploaded to S3
- [ ] CloudFront cache invalidated
- [ ] Can access dashboard URL
- [ ] Login flow works
- [ ] API calls successful
- [ ] No console errors

## 🔄 Re-deployment

For subsequent updates:

```bash
# 1. Make changes to code
# 2. Build
npm run build

# 3. Deploy
aws s3 sync dist/ s3://$BUCKET_NAME/ --delete
aws cloudfront create-invalidation --distribution-id $DISTRIBUTION_ID --paths "/*"
```

Or use the provided script:

```bash
npm run deploy
```

## 🎯 CI/CD Integration

For automated deployments, add to your pipeline:

```yaml
# Example GitHub Actions
- name: Build Frontend
  run: |
    cd admin-dashboard
    npm ci
    npm run build

- name: Deploy to S3
  run: |
    aws s3 sync admin-dashboard/dist/ s3://${{ secrets.BUCKET_NAME }}/ --delete

- name: Invalidate CloudFront
  run: |
    aws cloudfront create-invalidation \
      --distribution-id ${{ secrets.DISTRIBUTION_ID }} \
      --paths "/*"
```
