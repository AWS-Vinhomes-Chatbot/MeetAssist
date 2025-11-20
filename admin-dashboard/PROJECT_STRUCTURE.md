# Admin Dashboard Structure

## 📁 Complete Project Structure

```
admin-dashboard/
├── public/
│   └── favicon.ico                    # App icon
│
├── src/
│   ├── components/                    # Reusable UI components
│   │   ├── Button.tsx                # Button component with variants
│   │   ├── Card.tsx                  # Card and StatCard components
│   │   ├── Header.tsx                # Page header component
│   │   ├── Modal.tsx                 # Modal dialog component
│   │   └── Sidebar.tsx               # Navigation sidebar
│   │
│   ├── pages/                        # Page components
│   │   ├── OverviewPage.tsx          # Dashboard overview with stats
│   │   ├── ConversationsPage.tsx     # Conversation history management
│   │   ├── AnalyticsPage.tsx         # Analytics and reports
│   │   └── CrawlerPage.tsx           # Data sync management
│   │
│   ├── services/                     # API and service layer
│   │   ├── api.service.ts            # Base API service with auth
│   │   ├── auth.service.ts           # Cognito authentication
│   │   ├── conversation.service.ts   # Conversation API calls
│   │   ├── analytics.service.ts      # Analytics API calls
│   │   └── crawler.service.ts        # Crawler API calls
│   │
│   ├── types/                        # TypeScript type definitions
│   │   └── index.ts                  # All interfaces and types
│   │
│   ├── utils/                        # Utility functions
│   │   └── (add as needed)
│   │
│   ├── aws-exports.ts                # ⭐ AWS configuration
│   ├── App.tsx                       # Main app with routing
│   ├── main.tsx                      # React entry point
│   └── index.css                     # Global styles (Tailwind)
│
├── .env.example                      # Environment variables template
├── .env                              # ⚠️ Your actual config (git-ignored)
├── .gitignore                        # Git ignore rules
│
├── index.html                        # HTML entry point
├── package.json                      # Dependencies and scripts
├── vite.config.ts                    # Vite configuration
├── tsconfig.json                     # TypeScript configuration
├── tsconfig.node.json                # TypeScript config for Vite
├── tailwind.config.js                # Tailwind CSS configuration
├── postcss.config.js                 # PostCSS configuration
│
├── deploy.sh                         # Deployment script
├── DEPLOYMENT.md                     # Deployment guide
└── README.md                         # Project documentation
```

## 🔑 Key Files Explained

### Configuration Files

- **`aws-exports.ts`**: Most important file - contains all AWS service configurations
- **`.env`**: Environment-specific values (Cognito, API endpoints)
- **`vite.config.ts`**: Build tool configuration
- **`tailwind.config.js`**: Styling framework configuration

### Core Application

- **`main.tsx`**: React app initialization
- **`App.tsx`**: Main app component with routing and authentication logic
- **`index.css`**: Global styles using Tailwind CSS

### Services Layer

All API interactions go through services:
- `auth.service.ts` - Handles Cognito login/logout
- `api.service.ts` - Base service with authenticated requests
- Other services - Domain-specific API calls

### Components

Reusable UI components:
- `Button`, `Card`, `Modal` - Basic UI elements
- `Header`, `Sidebar` - Layout components

### Pages

Full page components:
- `OverviewPage` - Dashboard home
- `ConversationsPage` - List and filter conversations
- `AnalyticsPage` - Charts and metrics
- `CrawlerPage` - Data synchronization

## 🚀 Quick Start

```bash
# 1. Install dependencies
npm install

# 2. Configure environment
cp .env.example .env
# Edit .env with your AWS values

# 3. Run development server
npm run dev

# 4. Build for production
npm run build

# 5. Deploy to S3
./deploy.sh
```

## 📦 Available Scripts

```json
{
  "dev": "vite",                    // Start dev server on port 3000
  "build": "tsc && vite build",     // Build for production
  "preview": "vite preview",        // Preview production build
  "lint": "eslint . --ext ts,tsx"   // Run linter
}
```

## 🔧 Development Workflow

1. **Local Development**
   ```bash
   npm run dev
   # Set VITE_DEMO_MODE=true to skip AWS authentication
   ```

2. **Make Changes**
   - Edit components in `src/components/`
   - Update pages in `src/pages/`
   - Modify services in `src/services/`

3. **Build & Test**
   ```bash
   npm run build
   npm run preview
   ```

4. **Deploy**
   ```bash
   ./deploy.sh <bucket-name> <distribution-id>
   ```

## 📋 Environment Setup

Required environment variables in `.env`:

```env
# Cognito (from CDK outputs)
VITE_USER_POOL_ID=us-east-1_XXXXXXXXX
VITE_USER_POOL_CLIENT_ID=XXXXXXXXXX
VITE_COGNITO_DOMAIN=your-domain.auth.us-east-1.amazoncognito.com

# API Gateway (from CDK outputs)
VITE_API_ENDPOINT=https://xxxxx.execute-api.us-east-1.amazonaws.com/prod

# OAuth redirects (your CloudFront/custom domain)
VITE_REDIRECT_SIGN_IN=https://admin.meetassist.ai/
VITE_REDIRECT_SIGN_OUT=https://admin.meetassist.ai/

# Development
VITE_DEMO_MODE=false
```

## 🎨 Styling

Uses **Tailwind CSS** for styling:
- Utility-first CSS framework
- Configured in `tailwind.config.js`
- Custom colors and theme in config
- Global styles in `index.css`

## 🔐 Authentication Flow

1. User visits dashboard
2. Redirected to Cognito Hosted UI
3. After login, Cognito redirects back with code
4. App exchanges code for JWT tokens
5. Tokens stored in session
6. All API calls include Authorization header

## 📊 Features Implemented

✅ AWS Cognito authentication  
✅ Protected routes  
✅ Responsive sidebar navigation  
✅ Overview dashboard with stats  
✅ API service layer  
✅ TypeScript type safety  
✅ Tailwind CSS styling  
✅ Build optimization  
✅ CloudFront deployment  

## 🔜 Next Steps (To be implemented)

- [ ] Complete Conversations page with filters
- [ ] Implement Analytics charts (Chart.js)
- [ ] Add CSV export functionality
- [ ] Implement real-time updates
- [ ] Add error boundaries
- [ ] Add loading states
- [ ] Add tests (Jest + React Testing Library)
- [ ] Add Storybook for components

## 📝 Notes

- TypeScript errors during development are normal until dependencies are installed
- Run `npm install` to resolve all import errors
- Demo mode (`VITE_DEMO_MODE=true`) allows testing without AWS
- Always rebuild after changing `.env` variables
- CloudFront cache invalidation takes 1-5 minutes
