#!/bin/bash
# Deploy script for Webhook stack testing

echo "🚀 Deploying Webhook Test Stack..."
echo ""

# Check if SSM parameters exist
echo "📋 Checking required SSM parameters..."
aws ssm get-parameter --name "/meetassist/facebook/app_id" --query "Parameter.Value" --output text 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  Parameter /meetassist/facebook/app_id not found"
    echo "Creating placeholder parameter..."
    aws ssm put-parameter \
        --name "/meetassist/facebook/app_id" \
        --value "YOUR_FACEBOOK_APP_ID" \
        --type String \
        --description "Facebook App ID for Messenger Bot"
fi

aws ssm get-parameter --name "/meetassist/facebook/app_secret" --with-decryption --query "Parameter.Value" --output text 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  Parameter /meetassist/facebook/app_secret not found"
    echo "Creating placeholder parameter..."
    aws ssm put-parameter \
        --name "/meetassist/facebook/app_secret" \
        --value "YOUR_FACEBOOK_APP_SECRET" \
        --type SecureString \
        --description "Facebook App Secret for Messenger Bot"
fi

# Check if Secrets Manager secret exists
echo ""
echo "📋 Checking Secrets Manager secret..."
aws secretsmanager describe-secret --secret-id "meetassist/facebook/page_token" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  Secret meetassist/facebook/page_token not found"
    echo "Creating placeholder secret..."
    aws secretsmanager create-secret \
        --name "meetassist/facebook/page_token" \
        --description "Facebook Page Access Token for Messenger Bot" \
        --secret-string '{"page_token":"YOUR_PAGE_TOKEN","verify_token":"YOUR_VERIFY_TOKEN"}'
fi

echo ""
echo "✅ Prerequisites ready"
echo ""

# Synthesize the stack
echo "🔨 Synthesizing CDK stack..."
cdk synth -a "python app_webhook_test.py" WebhookTestStack

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Synthesis successful!"
    echo ""
    echo "📦 Deploying stack..."
    cdk deploy -a "python app_webhook_test.py" WebhookTestStack --require-approval never
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ Deployment successful!"
        echo ""
        echo "📝 Next steps:"
        echo "1. Update SSM parameters with real Facebook credentials"
        echo "2. Get the WebhookUrl from stack outputs"
        echo "3. Configure webhook in Facebook Developer Dashboard"
        echo "4. Test with: ./test_webhook.sh"
    else
        echo ""
        echo "❌ Deployment failed!"
        exit 1
    fi
else
    echo ""
    echo "❌ Synthesis failed!"
    exit 1
fi
