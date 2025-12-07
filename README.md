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
1. Type "aws configuration" in your terminal. Make sure you have created CLI secret access key for your account
2. Complete the configuration form. Be careful, region must be ap-northeast-1 



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
(Add your chatbot usage instructions here.)


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







