# Test script for Webhook Lambda function

Write-Host "🧪 Testing Webhook Lambda Function..." -ForegroundColor Cyan
Write-Host ""

# Get stack outputs
Write-Host "📋 Getting stack outputs..." -ForegroundColor Yellow
$webhookUrl = aws cloudformation describe-stacks --stack-name WebhookTestStack --query "Stacks[0].Outputs[?OutputKey=='WebhookUrl'].OutputValue" --output text

if ([string]::IsNullOrEmpty($webhookUrl)) {
    Write-Host "❌ Could not find WebhookUrl output. Is the stack deployed?" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Webhook URL: $webhookUrl" -ForegroundColor Green
Write-Host ""

# Test 1: Webhook Verification (GET)
Write-Host "Test 1: Webhook Verification (GET request)" -ForegroundColor Cyan
Write-Host "----------------------------------------" -ForegroundColor Gray

$verifyToken = "test_verify_token_12345"
$challenge = "test_challenge_12345"
$verifyUrl = "${webhookUrl}?hub.mode=subscribe&hub.challenge=$challenge&hub.verify_token=$verifyToken"

Write-Host "Request: GET $verifyUrl" -ForegroundColor Gray

try {
    $response = Invoke-WebRequest -Uri $verifyUrl -Method Get -UseBasicParsing
    
    if ($response.Content -eq $challenge) {
        Write-Host "✅ Test 1 PASSED: Received challenge back" -ForegroundColor Green
        Write-Host "   Response: $($response.Content)" -ForegroundColor Gray
    } else {
        Write-Host "⚠️  Test 1 WARNING: Unexpected response" -ForegroundColor Yellow
        Write-Host "   Expected: $challenge" -ForegroundColor Gray
        Write-Host "   Received: $($response.Content)" -ForegroundColor Gray
    }
} catch {
    Write-Host "❌ Test 1 FAILED: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""

# Test 2: Messenger Event (POST)
Write-Host "Test 2: Messenger Message Event (POST request)" -ForegroundColor Cyan
Write-Host "----------------------------------------" -ForegroundColor Gray

$messagePayload = @{
    object = "page"
    entry = @(
        @{
            id = "PAGE_ID"
            time = [int][double]::Parse((Get-Date -UFormat %s))
            messaging = @(
                @{
                    sender = @{ id = "1234567890" }
                    recipient = @{ id = "PAGE_ID" }
                    timestamp = [int][double]::Parse((Get-Date -UFormat %s))
                    message = @{
                        mid = "test_message_id"
                        text = "Hello bot!"
                    }
                }
            )
        }
    )
} | ConvertTo-Json -Depth 10

Write-Host "Request: POST $webhookUrl" -ForegroundColor Gray
Write-Host "Payload:" -ForegroundColor Gray
Write-Host $messagePayload -ForegroundColor DarkGray

try {
    $response = Invoke-WebRequest -Uri $webhookUrl -Method Post -Body $messagePayload -ContentType "application/json" -UseBasicParsing
    
    if ($response.StatusCode -eq 200) {
        Write-Host "✅ Test 2 PASSED: Status 200 OK" -ForegroundColor Green
        Write-Host "   Response: $($response.Content)" -ForegroundColor Gray
    } else {
        Write-Host "⚠️  Test 2 WARNING: Status $($response.StatusCode)" -ForegroundColor Yellow
        Write-Host "   Response: $($response.Content)" -ForegroundColor Gray
    }
} catch {
    Write-Host "❌ Test 2 FAILED: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""

# Test 3: OAuth Callback (GET)
Write-Host "Test 3: OAuth Callback (GET request)" -ForegroundColor Cyan
Write-Host "----------------------------------------" -ForegroundColor Gray

$callbackUrl = $webhookUrl -replace "/webhook", "/callback"
$authCode = "test_auth_code_12345"
$state = '{"psid":"1234567890"}' | ConvertTo-Json -Compress
$callbackTestUrl = "${callbackUrl}?code=$authCode&state=$state"

Write-Host "Request: GET $callbackTestUrl" -ForegroundColor Gray

try {
    $response = Invoke-WebRequest -Uri $callbackTestUrl -Method Get -UseBasicParsing
    
    if ($response.StatusCode -eq 200 -or $response.StatusCode -eq 400) {
        Write-Host "✅ Test 3 PASSED: Callback endpoint is accessible" -ForegroundColor Green
        Write-Host "   Status: $($response.StatusCode)" -ForegroundColor Gray
    } else {
        Write-Host "⚠️  Test 3 WARNING: Status $($response.StatusCode)" -ForegroundColor Yellow
    }
} catch {
    if ($_.Exception.Response.StatusCode -eq 400) {
        Write-Host "✅ Test 3 PASSED: Callback endpoint is accessible (400 expected for invalid code)" -ForegroundColor Green
    } else {
        Write-Host "❌ Test 3 FAILED: $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "🏁 Testing Complete!" -ForegroundColor Cyan
Write-Host ""
Write-Host "📝 Check CloudWatch Logs for detailed Lambda execution logs:" -ForegroundColor Yellow
Write-Host "   aws logs tail /aws/lambda/MessengerWebhookHandler --follow" -ForegroundColor Gray
Write-Host ""
Write-Host "📝 Update credentials before using with Facebook:" -ForegroundColor Yellow
Write-Host "   1. aws ssm put-parameter --name '/meetassist/facebook/app_id' --value 'YOUR_APP_ID' --overwrite" -ForegroundColor Gray
Write-Host "   2. aws ssm put-parameter --name '/meetassist/facebook/app_secret' --value 'YOUR_SECRET' --type SecureString --overwrite" -ForegroundColor Gray
Write-Host "   3. aws secretsmanager put-secret-value --secret-id 'meetassist/facebook/page_token' --secret-string '{\"page_token\":\"YOUR_TOKEN\",\"verify_token\":\"YOUR_VERIFY\"}'" -ForegroundColor Gray
