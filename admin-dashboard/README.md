# Admin Dashboard - React + TypeScript + Vite

Modern admin dashboard for managing chatbot conversations, analytics, and data synchronization.

## 🏗️ Architecture

Built with:
- **React 18** - UI library
- **TypeScript** - Type safety
- **Vite** - Fast build tool
- **Tailwind CSS** - Styling
- **AWS Amplify** - Authentication
- **Chart.js** - Data visualization
- **React Router** - Navigation

## 📁 Project Structure

```
admin-dashboard/
├── public/                 # Static assets
├── src/
│   ├── components/        # Reusable UI components
│   │   ├── Button.tsx
│   │   ├── Card.tsx
│   │   ├── Header.tsx
│   │   ├── Modal.tsx
│   │   └── Sidebar.tsx
│   ├── pages/            # Page components
│   │   ├── OverviewPage.tsx
│   │   ├── ConversationsPage.tsx
│   │   ├── AnalyticsPage.tsx
│   │   └── CrawlerPage.tsx
│   ├── services/         # API services
│   │   ├── auth.service.ts
│   │   ├── api.service.ts
│   │   ├── conversation.service.ts
│   │   ├── analytics.service.ts
│   │   └── crawler.service.ts
│   ├── types/           # TypeScript definitions
│   │   └── index.ts
│   ├── utils/           # Utility functions
│   ├── aws-exports.ts   # AWS configuration
│   ├── App.tsx          # Main app component
│   ├── main.tsx         # Entry point
│   └── index.css        # Global styles
├── .env.example         # Environment variables template
├── package.json
├── vite.config.ts
├── tailwind.config.js
└── tsconfig.json
```

## 🚀 Getting Started

### Prerequisites

- Node.js 18+ and npm
- AWS account with deployed CDK stack

### Installation

1. **Install dependencies:**
   ```bash
   cd admin-dashboard
   npm install
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   ```

3. **Update `.env` with values from CDK deployment:**
   - `VITE_USER_POOL_ID` - From CDK Output: `CognitoUserPoolId`
   - `VITE_USER_POOL_CLIENT_ID` - From CDK Output: `CognitoAppClientId`
   - `VITE_COGNITO_DOMAIN` - From Cognito Console
   - `VITE_API_ENDPOINT` - From CDK Output: `AdminApiEndpoint`

### Development

```bash
# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

### Demo Mode

For local development without AWS:

```bash
# In .env
VITE_DEMO_MODE=true
```

## 📝 Key Features

### 1. Overview Dashboard
- Real-time statistics
- Trend charts (last 7 days)
- Status distribution
- Quick actions

### 2. Conversations Management
- Filter by date, user, status
- View conversation details
- Export to CSV

### 3. Analytics
- Date range analysis
- Daily analytics charts
- Top queries
- Performance metrics

### 4. Data Sync (Glue Crawler)
- Start crawler
- Monitor status
- View crawler stats

## 🔐 Authentication Flow

1. User clicks "Login with Cognito"
2. Redirects to Cognito Hosted UI
3. User enters credentials
4. Cognito redirects back with authorization code
5. App exchanges code for tokens
6. Tokens stored in session

## 🌐 Deployment to S3/CloudFront

Build and deploy:

```bash
# Build production bundle
npm run build

# Output will be in dist/ directory
# Upload dist/ contents to S3 bucket configured in CDK
```

The CDK stack automatically:
- Creates S3 bucket
- Sets up CloudFront distribution
- Configures custom domain (admin.meetassist.ai)
- Deploys built files

## 📋 Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `VITE_USER_POOL_ID` | Cognito User Pool ID | `us-east-1_XXXXXXXXX` |
| `VITE_USER_POOL_CLIENT_ID` | Cognito App Client ID | `XXXXXXXXXX` |
| `VITE_COGNITO_DOMAIN` | Cognito Hosted UI domain | `yourapp.auth.region.amazoncognito.com` |
| `VITE_API_ENDPOINT` | API Gateway URL | `https://xxxxx.execute-api.us-east-1.amazonaws.com/prod` |
| `VITE_REDIRECT_SIGN_IN` | OAuth redirect (login) | `https://admin.meetassist.ai/` |
| `VITE_REDIRECT_SIGN_OUT` | OAuth redirect (logout) | `https://admin.meetassist.ai/` |
| `VITE_DEMO_MODE` | Enable demo mode | `false` |

## 🔧 Troubleshooting

### Issue: "Missing AWS configuration"
**Solution:** Ensure all required environment variables are set in `.env`

### Issue: OAuth redirect not working
**Solution:** Verify callback URLs in Cognito match exactly (including trailing slash)

### Issue: API calls failing
**Solution:** Check CORS configuration in API Gateway and verify tokens are valid

## 📦 Build Output

Production build creates optimized bundles:
- Code splitting for faster loads
- Tree shaking for smaller bundles
- Minified CSS and JS
- Source maps (optional)

## 🤝 Contributing

1. Create feature branch
2. Make changes
3. Test thoroughly
4. Submit pull request

## 📄 License

Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
SPDX-License-Identifier: MIT-0
