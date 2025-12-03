# Lưu Facebook App ID
aws ssm put-parameter \
  --name "/meetassist/facebook/app_id" \
  --value "123456789012345" \
  --type String

# Lưu Facebook App Secret (encrypted)
aws ssm put-parameter --name "/meetassist/facebook/app_secret" --value "EAAU7ZC4FkKAEBQMNMP29iZCVuiPdPzz5afmagBrCq6yvnOw08jyfx6W5OJHMvgxQOfBYQ1pg4swGC06rItuftcND5Va6QhTaP8cGnGUch02XjVF3IPVT5LanRXuZB0z3lXvn2YOasUSGlL1lM9ZCGRZAVTVQkmJnMEFcnGskMQEGrIGKfduVkMK2ypLxQzOjK8vXlWOsd" --type String --overwrite --output json
# ma facebook
# secret:
EAAU7ZC4FkKAEBQMNMP29iZCVuiPdPzz5afmagBrCq6yvnOw08jyfx6W5OJHMvgxQOfBYQ1pg4swGC06rItuftcND5Va6QhTaP8cGnGUch02XjVF3IPVT5LanRXuZB0z3lXvn2YOasUSGlL1lM9ZCGRZAVTVQkmJnMEFcnGskMQEGrIGKfduVkMK2ypLxQzOjK8vXlWOsd
 1473343457077249
# link:

<!-- WebhookTestStack.CallbackUrl = https://7zg5hg13e7.execute-api.ap-southeast-1.amazonaws.com/prod/callback
WebhookTestStack.CognitoHostedUIUrl = https://meetassist-395118572884-ap-southeast-1.auth.ap-southeast-1.amazoncognito.com/login?client_id=3jfhadfppif2ph5hf0nlmjgabd&response_type=code&redirect_uri=https://7zg5hg13e7.execute-api.ap-southeast-1.amazonaws.com/prod/callback
WebhookTestStack.FacebookOAuthRedirectUri = https://meetassist-395118572884-ap-southeast-1.auth.ap-southeast-1.amazoncognito.com/oauth2/idpresponse
WebhookTestStack.MessengerApiEndpoint974EFA90 = https://7zg5hg13e7.execute-api.ap-southeast-1.amazonaws.com/prod/
WebhookTestStack.SessionTableName = WebhookTestStack-SessionTableA016F679-1HNH1TY6FPKPC
WebhookTestStack.UserPoolClientId = 3jfhadfppif2ph5hf0nlmjgabd
WebhookTestStack.UserPoolId = ap-southeast-1_bOcAGB90L
WebhookTestStack.WebhookUrl = https://7zg5hg13e7.execute-api.ap-southeast-1.amazonaws.com/prod/webhook  
Stack ARN:
arn:aws:cloudformation:ap-southeast-1:395118572884:stack/WebhookTestStack/8857b390-c777-11f0-a745-02f0cb03bf6f -->
aws cognito-idp describe-user-pool-client --user-pool-id <ap-southeast-1_bOcAGB90L> --client-id <3jfhadfppif2ph5hf0nlmjgabd> --query 'UserPoolClient.ClientSecret' --output text | ForEach-Object { aws ssm put-parameter --name /meetassist/cognito/client_secret --value $_ --type SecureString --overwrite }
