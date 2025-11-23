# Deploy script for Webhook stack testing (PowerShell)

Write-Host "🚀 Deploying Webhook Test Stack..." -ForegroundColor Cyan
Write-Host ""

# Check if SSM parameters exist
Write-Host "📋 Checking required SSM parameters..." -ForegroundColor Yellow

try {
    $appId = aws ssm get-parameter --name "/meetassist/facebook/app_id" --query "Parameter.Value" --output text 2>$null
    if ($LASTEXITCODE -ne 0) { throw }
    Write-Host "✅ Found: /meetassist/facebook/app_id" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Parameter /meetassist/facebook/app_id not found" -ForegroundColor Yellow
    Write-Host "Creating placeholder parameter..."
    aws ssm put-parameter `
        --name "/meetassist/facebook/app_id" `
        --value "103575692353867" `
        --type String `
        --description "Facebook App ID for Messenger Bot" `
        --overwrite
        
}

try {
    $appSecret = aws ssm get-parameter --name "/meetassist/facebook/app_secret" --with-decryption --query "Parameter.Value" --output text 2>$null
    if ($LASTEXITCODE -ne 0) { throw }
    Write-Host "✅ Found: /meetassist/facebook/app_secret" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Parameter /meetassist/facebook/app_secret not found" -ForegroundColor Yellow
    Write-Host "Creating placeholder parameter..."
    aws ssm put-parameter `
        --name "/meetassist/facebook/app_secret" `
        --value "EAAU7ZC4FkKAEBP3I7YwDZAwmhj5f7JsAfTB8nS5xbnZAlSX2LCx5HH8AkjzgjdnkMCxyoUKW5hiVW4UlSb2bRqV5EZApwCwR4Rnc0JnR9Vfo264ZBYUltWZC7AP2hVZA65jJTqmE68G9JHZBeGTiZCTUUmUWvsoNkx4hYQWNjaGgco3uEOqiPadQBT1tNM0NlSgXDCGUgBiD4" `
        --type SecureString `
        --description "Facebook App Secret for Messenger Bot" `
        --overwrite
        
}

# Check if Secrets Manager secret exists
Write-Host ""
Write-Host "📋 Checking Secrets Manager secret..." -ForegroundColor Yellow

try {
    $secret = aws secretsmanager describe-secret --secret-id "meetassist/facebook/page_token" 2>$null
    if ($LASTEXITCODE -ne 0) { throw }
    Write-Host "✅ Found: meetassist/facebook/page_token" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Secret meetassist/facebook/page_token not found" -ForegroundColor Yellow
    Write-Host "Creating placeholder secret..."
    aws secretsmanager create-secret `
        --name "meetassist/facebook/page_token" `
        --description "Facebook Page Access Token for Messenger Bot" `
        --secret-string '{\"page_token\":\"YOUR_PAGE_TOKEN\",\"verify_token\":\"YOUR_VERIFY_TOKEN\"}'
}

Write-Host ""
Write-Host "✅ Prerequisites ready" -ForegroundColor Green
Write-Host ""

# Synthesize the stack
Write-Host "🔨 Synthesizing CDK stack..." -ForegroundColor Cyan
cdk synth -a "python app_webhook_test.py" WebhookTestStack

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ Synthesis successful!" -ForegroundColor Green
    Write-Host ""
    Write-Host "📦 Deploying stack..." -ForegroundColor Cyan
    cdk deploy -a "python app_webhook_test.py" WebhookTestStack --require-approval never
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "✅ Deployment successful!" -ForegroundColor Green
        Write-Host ""
        Write-Host "📝 Next steps:" -ForegroundColor Yellow
        Write-Host "1. Update SSM parameters with real Facebook credentials"
        Write-Host "2. Get the WebhookUrl from stack outputs"
        Write-Host "3. Configure webhook in Facebook Developer Dashboard"
        Write-Host "4. Test with: .\test_webhook.ps1"
    } else {
        Write-Host ""
        Write-Host "❌ Deployment failed!" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host ""
    Write-Host "❌ Synthesis failed!" -ForegroundColor Red
    exit 1
}
