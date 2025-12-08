# MeetAssist text-to-SQL chatbot using Amazon Bedrock, Amazon DynamoDB, and Amazon RDS

To manually create a virtualenv on macOS and Linux:

```
$ python3 -m venv .venv
```

After the init process completes and the virtualenv is created, you can use the following
step to activate your virtualenv.

```
$ source .venv/bin/activate
```

If you are a Windows platform, you would activate the virtualenv like this:

```
% .venv\Scripts\activate.bat
```

Once the virtualenv is activated, you can install the required dependencies.

```
$ pip install -r requirements.txt
```

## Prerequisites
The following are needed in order to proceed with this post:

* An [AWS account](https://aws.amazon.com/).
* A [Facebook account](https://www.facebook.com/) connected to [Facebook Developers](https://developers.facebook.com/) for creating the Messenger chatbot.
* A [Facebook Page](https://www.facebook.com/pages/creation/) that will be used to host the chatbot (create a new page or use an existing one).
* A [Git client](https://git-scm.com/downloads) to clone the source code provided.
* [Docker](https://www.docker.com/) installed and running on the local host or laptop.
* [Install AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/getting-started.html)
* The [AWS Command Line Interface (AWS CLI)](https://aws.amazon.com/cli/).
* The AWS Systems Manager [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html).
* [Amazon Bedrock model access](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html) enabled for Anthropic Claude 3.5 Sonnet, Claude 3 Sonnet, Claude 3 Haiku and Amazon Titan Embeddings G1 – Text in the ap-northeast-1 Region.
* Python 3.12 or higher with the pip package manager.
* Node.js (version 18.x or higher) and npm – required for running the dashboard, installing dependencies, and building workshop assets.


## Enabling Bedrock Models

1. Search for Amazon Bedrock in AWS Console 
2. Access Model catalog 
3. Choose the corresponding model name (Anthropic Claude 3.5 Sonnet, Claude 3 Sonnet, Claude 3 Haiku and Amazon Titan Embeddings G1) 
4. Select "Open in playground" and send a message to enable it
  
 

The dependencies for the MeetAssist code solution, and custom resource to initialize the database, include their respective requirements.txt file that are installed as part of the CDK deployment.

# Usage
## Configuration AWS CLI
1. Type `aws configure` in your terminal. Make sure you have created CLI secret access key for your account (recommend using an IAM account with admin privileges)
2. Complete the configuration form:
   - AWS Access Key ID: Your access key
   - AWS Secret Access Key: Your secret key
   - Default region name: `ap-northeast-1`
   - Default output format: `json`

**Note:** To create IAM access keys, go to AWS Console → IAM → Users → Your User → Security Credentials → Create Access Key 


## Download the dataset and upload to Amazon S3

1. Navigate to the [MeetAssistData](https://drive.google.com/drive/folders/1JQ9X9BbKL7q82sEifvN5Seas7Mrgh4Q7?usp=sharing), and download the data to your local machine.
2. Unzip the file, which will expand into a file called `DATA`.
3. Run this CLI script to create this project's Amazon Simple Storage Service (Amazon S3) bucket format. Replace <account-id> and  with your AWS account ID.
```
aws s3 mb s3://meetassist-data-<account-id>-ap-northeast-1 --region ap-northeast-1
```
3. Create a folder named "data" in the S3 bucket and upload all CSV files into it


## Deploy the solution

1. Clone the repository from GitHub:
```
git clone https://github.com/AWS-Vinhomes-Chatbot/MeetAssist
cd MeetAssist
```

2. Build the dashboard first. Follow the steps below: 

### Navigate to frontend folder
```
cd frontend
```

### Install dependencies
Run the following command to install all necessary libraries:
```
npm i
```

### Build the Dashboard
After the installation is complete, run the build command:
```
npm run build
```
Once the process completes, a dist directory will be created, containing the index.html file and the assets folder.


### Use this command to return to the project’s root folder:
```
cd ..
```

3. Deploy the CDK application. It will take about 20-30 minutes to deploy all of the resources. 
```
cdk bootstrap aws://{{account_id}}/ap-northeast-1 
cdk deploy --all 
```
Note: if you receive an error at this step, please ensure Docker is running on the local host or laptop.


4. After the CDK deployment completes, you must run the DataIndexer Lambda function to populate the embeddings table with database schema information. Use the following AWS CLI command:

```
aws lambda invoke --function-name DataIndexerStack-DataIndexerFunction --invocation-type Event response.json --region example:aws lambda invoke --function-name DataIndexerStack-DataIndexerFunction --invocation-type Event response.json --region ap-northeast-1
```

5. After completing all the steps above, your environment is fully deployed and initialized. You can now start using both the MeetAssist chatbot and the Admin Dashboard. The instructions for each are provided in the sections below.



# Using the MeetAssist Chatbot

The MeetAssist chatbot is integrated with Facebook Messenger, allowing users to interact naturally to book, update, or cancel appointments.

## Setting Up the Messenger Chatbot

### 1. Create a Facebook App 

1. Go to [Facebook Developers](https://developers.facebook.com/)
2. Click **"My Apps"** → **"Create App"**
3. Fill in your app name (e.g., `MeetAssist`) and App Contact Email → Click **"Next"**
4. Select **"Messaging businesses"** as your use case → Click **"Next"**
5. Select your **"Business"** profile or choose none if you just want to test the app → Click **"Next"**
6. Click **"Go to Dashboard"**

### 2. Configure App Settings

1. In your app dashboard, click **"App Settings"** → **"Basic"**
2. Copy and save your **App ID** and **App Secret**
3. Paste the Privacy Policy URL: `https://www.freeprivacypolicy.com/live/e7193dae-4bba-4482-876e-7b76d83a0676`
4. Select **"Messenger for Business"** as the app category → Click **"Save Changes"**

### 3. Store Facebook Credentials in AWS

Run the following AWS CLI commands to securely store your Facebook credentials:

#### Create SSM Parameters:

```powershell
# Facebook App ID
aws ssm put-parameter `
    --name "/meetassist/facebook/app_id" `
    --value "YOUR_FACEBOOK_APP_ID" `
    --type "String" `
    --description "Facebook App ID for MeetAssist" `
    --region ap-northeast-1

# Facebook App Secret
aws ssm put-parameter `
    --name "/meetassist/facebook/app_secret" `
    --value "YOUR_FACEBOOK_APP_SECRET" `
    --type "String" `
    --description "Facebook App Secret for MeetAssist" `
    --region ap-northeast-1
```

#### Create Secrets Manager Secrets:

```powershell
# Facebook Page Access Token (get this from step 4 below)
aws secretsmanager create-secret `
    --name "meetassist/facebook/page_token" `
    --description "Facebook Page Access Token for MeetAssist" `
    --secret-string "YOUR_FACEBOOK_PAGE_ACCESS_TOKEN" `
    --region ap-northeast-1

# Facebook Verify Token (create a random string, e.g., "my_secure_token_12345")
aws secretsmanager create-secret `
    --name "/meetassist/facebook/verify_token" `
    --description "Facebook Webhook Verify Token for MeetAssist" `
    --secret-string "YOUR_CUSTOM_VERIFY_TOKEN_123456" `
    --region ap-northeast-1
```

**Note:** Replace `YOUR_FACEBOOK_APP_ID`, `YOUR_FACEBOOK_APP_SECRET`, `YOUR_FACEBOOK_PAGE_ACCESS_TOKEN`, and `YOUR_CUSTOM_VERIFY_TOKEN_123456` with your actual values.

### 4. Connect Facebook Page and Get Page Access Token

1. In your app dashboard, click **"Use Cases"** → **"Customize"**
2. Go to **"Messenger API Settings"**, under **"Generate Access Token"** click **"Connect"**
3. Link your Facebook Page to the app
4. Copy the **Page Access Token** that is generated
5. Use this token in the `aws secretsmanager create-secret` command above

### 5. Configure Webhooks API

1. Get your Webhook URL from the `outputs.json` file (generated after CDK deployment)
2. In your app dashboard, go to **"Messenger API Settings"**
3. Under **"Webhooks"** section, click **"Add Callback URL"**
4. Enter the following:
   - **Callback URL**: `https://<your-api-gateway-url>/webhook` (from `outputs.json`)
   - **Verify Token**: The same random string you used in step 3 (e.g., `YOUR_CUSTOM_VERIFY_TOKEN_123456`)
5. Click **"Verify and Save"**
6. Subscribe to the following webhook fields:
   - `messages`
   - `messaging_postbacks`
   - `messaging_account_linking`

### 7. Subscribe Page to Your App

1. In **"Messenger API Settings"**, scroll to **"Webhooks"** section
2. Click **"Add or Remove Pages"**
3. Select your Facebook Page and click **"Subscribe"**

### 8. Configure Messenger Profile (Get Started Button & Greeting)

After deployment, the chatbot automatically configures:
- **Get Started Button**: Users click this to begin conversation
- **Greeting Text**: Welcome message shown before user starts chatting

To manually update if needed:

```bash
# Set Get Started Button
curl -X POST "https://graph.facebook.com/v18.0/me/messenger_profile?access_token=<PAGE_ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "get_started": {"payload": "GET_STARTED"}
  }'

# Set Greeting Text
curl -X POST "https://graph.facebook.com/v18.0/me/messenger_profile?access_token=<PAGE_ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "greeting": [
      {
        "locale": "default",
        "text": "Xin chào! Mình là MeetAssist, trợ lý đặt lịch hẹn tư vấn hướng nghiệp. Hãy nhấn \"Bắt đầu\" để sử dụng dịch vụ! 👋"
      }
    ]
  }'
```

### 9. App Mode and Permissions

**Important Notes:**

- **Development Mode**: Your app is currently in development mode. Only you (the app developer) and testers you add can interact with the bot.
- **Public Access**: To allow other users to use your bot, go to your app dashboard and switch the app to **"Live Mode"** under **"App Settings"** → **"Basic"**.
- **App Review**: For full features and permissions, you must complete Facebook's App Review process. For testing purposes only, App Review is not required.

## Using the Chatbot

### Authentication
1. Open your Facebook Page in Messenger
2. Click **"Get Started"** button
3. The bot will ask for your email
4. Enter your email (e.g., `user@example.com`)
5. You'll receive a 6-digit OTP code via email
6. Enter the OTP to authenticate
7. After successful authentication, you can start booking appointments

### Booking Appointments

The bot supports natural language conversations in Vietnamese for managing appointments:

**Create New Appointment:**
- Say: `"Tôi muốn đặt lịch"` or `"Đặt lịch hẹn"`
- The bot will ask for consultant name
- You can also ask: `"Cho xem danh sách tư vấn viên"` or `"Có tư vấn viên nào chuyên về [lĩnh vực]?"`
- Confirm the consultant, then select a time slot from the list
- Provide your name, phone number, and email
- Confirm the booking

**Update Appointment:**
- Say: `"Tôi muốn đổi lịch"` or `"Cập nhật lịch hẹn"`
- Select the appointment you want to change
- Provide new consultant information
- Confirm changes and select new time slot
- Confirm the update

**Cancel Appointment:**
- Say: `"Tôi muốn hủy lịch"` or `"Hủy lịch hẹn"`
- Select the appointment you want to cancel
- Confirm the cancellation

### General Queries

You can ask the bot various questions in Vietnamese:
- **Consultants**: `"Có tư vấn viên nào chuyên về tài chính?"` or `"Cho xem danh sách tư vấn viên"`
- **Available Slots**: `"Lịch trống của anh Nguyễn Văn A?"` or `"Cho xem lịch trống ngày mai"`
- **Your Appointments**: `"Cho xem lịch hẹn của tôi"` or `"Tôi có lịch hẹn nào?"`
- **Quick Booking**: `"Đặt lịch với [tên tư vấn viên] lúc [giờ] ngày [ngày]"`

### Aborting Actions

At any time during booking, you can say:
- `"Thôi"`, `"Dừng"`, `"Hủy bỏ"`, `"Cancel"` to abort the current action

## Session Management

- **Session Timeout**: 30 minutes of inactivity
- **Booking Timeout**: 10 minutes for incomplete booking flows
- After timeout, you'll be notified and the session will reset

## Troubleshooting

**Issue: Bot doesn't respond**
- Check if your Facebook Page is subscribed to the webhook
- Verify the webhook callback URL is correct in Facebook App settings
- Check Lambda logs in CloudWatch for errors

**Issue: OTP not received**
- Verify Amazon SES is configured and your email is verified
- Check spam/junk folder
- **SES Sandbox Mode**: In sandbox mode, only verified email addresses can receive emails. You must verify recipient emails in SES Console.
- **SES Production Mode**: In production mode, you can send emails to any address without prior verification. [Request production access](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html) if needed.

**Issue: "System is busy" message**
- This indicates Amazon Bedrock throttling
- Wait 1 minute and try again
- If persistent, contact administrator to increase Bedrock quotas


# Using the Admin Dashboard

The Admin Dashboard is a comprehensive management interface that allows administrators to monitor system statistics, manage consultants, and oversee all appointments.

## Initial Setup

The Admin Dashboard requires an administrator account created in Amazon Cognito. Follow these steps to access the dashboard for the first time:

### 1. Create an Admin User

Run the following AWS CLI command to create an admin account:

```
aws cognito-idp admin-create-user --user-pool-id <your-user-pool-id> --username <your-email> --user-attributes Name=email,Value=<your-email> Name=email_verified,Value=true --temporary-password "<your-temporary-password>" --region ap-northeast-1
```

**Note:** Both the User Pool ID and the Admin Dashboard URL can be found in the `outputs.json` file generated after CDK deployment.

### 2. First Login

1. Open the Admin Dashboard URL from the `outputs.json` file
2. Log in with your email and temporary password
3. Cognito will prompt you to set a new permanent password
4. After updating your password, you will be redirected to the Admin Dashboard

## Dashboard Features

### Overview Page
- View system statistics: Total customers, consultants, appointments, and average ratings
- Appointments breakdown by status (Pending, Confirmed, Completed, Cancelled)
- Recent appointments list

### Consultants Management Page

**Consultant Management:**
- View, add, edit, and delete consultant profiles
- Manage consultant information (name, email, phone, specialties, qualifications)

**Account Management:**
- Create/delete Cognito accounts for consultant login
- Sync all consultant accounts with Cognito
- Reset consultant passwords

**Schedule Management:**
- View and manage consultant availability
- Add/edit/delete time slots (8 predefined slots from 8:00 AM to 9:30 PM)

### Appointments Management Page
- View all appointments with complete details
- Filter by status (All, Pending, Confirmed, Completed, Cancelled)
- Create, edit, and delete appointments



# Using the Consultant Dashboard

## Access
Consultants receive login credentials via email after the admin creates their Cognito account.

## Dashboard Features

### My Appointments Page
- View all appointments with customer details and status
- Filter by status (All, Pending, Confirmed, Completed, Cancelled)
- Confirm, complete, or cancel appointments
- Customers receive automatic email notifications

### My Schedule Page
- View weekly schedule (Monday to Sunday)
- Navigate between weeks
- See slot status: Available (green), Booked (blue), Pending (yellow), Past (gray), Unavailable (red)
- **Note**: Schedule is view-only. Contact admin to modify availability.







