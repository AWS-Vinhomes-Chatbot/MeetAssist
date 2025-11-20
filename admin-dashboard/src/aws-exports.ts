/**
 * AWS Configuration for Admin Dashboard
 * 
 * IMPORTANT: These values MUST be updated after CDK deployment
 * Get values from CDK Stack Outputs
 */

export const awsConfig = {
  // AWS Region
  region: 'us-east-1',
  
  // Cognito Configuration
  cognito: {
    userPoolId: process.env.VITE_USER_POOL_ID || 'us-east-1_XXXXXX',
    userPoolClientId: process.env.VITE_USER_POOL_CLIENT_ID || 'XXXXXXXXXX',
    domain: process.env.VITE_COGNITO_DOMAIN || 'bookingchatbotadminpool.auth.us-east-1.amazoncognito.com',
    
    // OAuth Configuration
    oauth: {
      domain: process.env.VITE_COGNITO_DOMAIN || 'bookingchatbotadminpool.auth.us-east-1.amazoncognito.com',
      scope: ['openid', 'email', 'profile'],
      redirectSignIn: process.env.VITE_REDIRECT_SIGN_IN || 'https://admin.meetassist.ai/',
      redirectSignOut: process.env.VITE_REDIRECT_SIGN_OUT || 'https://admin.meetassist.ai/',
      responseType: 'code', // Use authorization code grant (recommended)
    },
  },
  
  // API Gateway Configuration
  api: {
    endpoint: process.env.VITE_API_ENDPOINT || 'https://XXXXX.execute-api.us-east-1.amazonaws.com/prod',
    adminPath: '/admin',
    crawlerPath: '/crawler',
  },
  
  // Application Configuration
  app: {
    name: 'Chatbot Admin Dashboard',
    version: '1.0.0',
    demoMode: process.env.VITE_DEMO_MODE === 'true', // Enable demo mode for testing
  },
} as const;

// Validate configuration
export const validateConfig = (): boolean => {
  const missingVars: string[] = [];
  
  if (awsConfig.cognito.userPoolId.includes('XXXX')) {
    missingVars.push('VITE_USER_POOL_ID');
  }
  
  if (awsConfig.cognito.userPoolClientId.includes('XXXX')) {
    missingVars.push('VITE_USER_POOL_CLIENT_ID');
  }
  
  if (awsConfig.api.endpoint.includes('XXXX')) {
    missingVars.push('VITE_API_ENDPOINT');
  }
  
  if (missingVars.length > 0 && !awsConfig.app.demoMode) {
    console.warn('⚠️ Missing AWS configuration:', missingVars.join(', '));
    console.warn('ℹ️ Set VITE_DEMO_MODE=true to use demo mode');
    return false;
  }
  
  return true;
};

export default awsConfig;
