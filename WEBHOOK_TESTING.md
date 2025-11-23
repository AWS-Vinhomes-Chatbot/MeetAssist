# Webhook Stack Testing Guide

## 📋 Prerequisites

1. **AWS CLI configured**
   ```powershell
   aws configure
   ```

2. **CDK installed**
   ```powershell
   npm install -g aws-cdk
   ```

3. **Python dependencies**
   ```powershell
   pip install -r requirements.txt
   ```

## 🚀 Quick Start

### Step 1: Deploy Webhook Stack

```powershell
# PowerShell
.\deploy_webhook.ps1
```

```bash
# Bash (Linux/Mac)
chmod +x deploy_webhook.sh
./deploy_webhook.sh
```

Or manually:
```powershell
cdk deploy -a "python app_webhook_test.py" WebhookTestStack
```

### Step 2: Get Stack Outputs

```powershell
aws cloudformation describe-stacks --stack-name WebhookTestStack --query "Stacks[0].Outputs"
```

You'll see:
- `WebhookUrl`: API Gateway webhook endpoint
- `CallbackUrl`: OAuth callback endpoint
- `CognitoHostedUIUrl`: Login URL
- `FacebookOAuthRedirectUri`: Add to Facebook App
- `UserPoolId`: Cognito User Pool ID
- `UserPoolClientId`: Cognito Client ID
- `SessionTableName`: DynamoDB table name

### Step 3: Update Credentials

```powershell
# Facebook App ID
aws ssm put-parameter `
  --name "/meetassist/facebook/app_id" `
  --value "YOUR_FACEBOOK_APP_ID" `
  --type String `
  --overwrite

# Facebook App Secret
aws ssm put-parameter `
  --name "/meetassist/facebook/app_secret" `
  --value "YOUR_FACEBOOK_APP_SECRET" `
  --type SecureString `
  --overwrite

# Facebook Page Token & Verify Token
aws secretsmanager put-secret-value `
  --secret-id "meetassist/facebook/page_token" `
  --secret-string '{
    "page_token": "YOUR_PAGE_ACCESS_TOKEN",
    "verify_token": "YOUR_VERIFY_TOKEN"
  }'
```

### Step 4: Test Lambda Function

```powershell
.\test_webhook.ps1
```

## 🧪 Manual Testing

### Test 1: Webhook Verification
```powershell
$webhookUrl = "https://YOUR_API_ID.execute-api.ap-southeast-1.amazonaws.com/prod/webhook"
$challenge = "test123"
$verifyToken = "YOUR_VERIFY_TOKEN"

curl "$webhookUrl?hub.mode=subscribe&hub.challenge=$challenge&hub.verify_token=$verifyToken"

# Expected: test123
```

### Test 2: Message Event
```powershell
$payload = @{
  object = "page"
  entry = @(
    @{
      messaging = @(
        @{
          sender = @{ id = "1234567890" }
          message = @{ text = "Hello" }
        }
      )
    }
  )
} | ConvertTo-Json -Depth 10

Invoke-WebRequest -Uri $webhookUrl -Method Post -Body $payload -ContentType "application/json"

# Expected: {"status": "EVENT_RECEIVED"}
```

### Test 3: Check Lambda Logs
```powershell
aws logs tail /aws/lambda/MessengerWebhookHandler --follow
```

## 🔧 Troubleshooting

### Error: Parameter not found
```powershell
# Create missing parameters
.\deploy_webhook.ps1
```

### Error: Secret not found
```powershell
aws secretsmanager create-secret `
  --name "meetassist/facebook/page_token" `
  --secret-string '{"page_token":"PLACEHOLDER","verify_token":"PLACEHOLDER"}'
```

### Error: Lambda timeout
```powershell
# Check logs
aws logs tail /aws/lambda/MessengerWebhookHandler --since 10m
```

### Error: Invalid signature
- Update Facebook App Secret in SSM
- Verify webhook is receiving correct headers

## 📊 Verify Deployment

### Check Lambda Function
```powershell
aws lambda get-function --function-name MessengerWebhookHandler
```

### Check API Gateway
```powershell
aws apigateway get-rest-apis --query "items[?name=='MessengerWebhookApi']"
```

### Check DynamoDB Table
```powershell
aws dynamodb describe-table --table-name $(aws cloudformation describe-stacks --stack-name WebhookTestStack --query "Stacks[0].Outputs[?OutputKey=='SessionTableName'].OutputValue" --output text)
```

### Check Cognito User Pool
```powershell
$poolId = aws cloudformation describe-stacks --stack-name WebhookTestStack --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" --output text
aws cognito-idp describe-user-pool --user-pool-id $poolId
```

## 🗑️ Cleanup

```powershell
cdk destroy -a "python app_webhook_test.py" WebhookTestStack
```

## 📝 Next Steps

1. ✅ Deploy stack
2. ✅ Test endpoints
3. ✅ Update credentials
4. 🔄 Configure Facebook webhook
5. 🔄 Test with real Messenger conversation

## 🔗 Useful Commands

```powershell
# Synthesize stack
cdk synth -a "python app_webhook_test.py" WebhookTestStack

# Check diff
cdk diff -a "python app_webhook_test.py" WebhookTestStack

# View stack events
aws cloudformation describe-stack-events --stack-name WebhookTestStack --max-items 10

# Invoke Lambda directly
aws lambda invoke --function-name MessengerWebhookHandler --payload '{"httpMethod":"GET","path":"/webhook","queryStringParameters":{"hub.mode":"subscribe","hub.challenge":"test","hub.verify_token":"test"}}' response.json
```

## 📚 Documentation

- [Facebook Messenger Webhook](https://developers.facebook.com/docs/messenger-platform/webhooks/)
- [AWS CDK Python](https://docs.aws.amazon.com/cdk/v2/guide/work-with-cdk-python.html)
- [Cognito User Pools](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-identity-pools.html)
