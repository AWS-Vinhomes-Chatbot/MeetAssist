/**
 * AWS Configuration for Admin Dashboard
 * 
 * IMPORTANT: These values MUST be updated after CDK deployment
 * Get values from CDK Stack Outputs
 */

export const config = {
  // AWS Region
  region: import.meta.env.VITE_AWS_REGION || 'us-east-1',
  
  // Cognito Configuration
  cognitoUserPoolId: import.meta.env.VITE_USER_POOL_ID || 'us-east-1_XXXXXX',
  cognitoClientId: import.meta.env.VITE_USER_POOL_CLIENT_ID || 'XXXXXXXXXX',
  cognitoDomain: import.meta.env.VITE_COGNITO_DOMAIN || 'bookingchatbotadminpool.auth.us-east-1.amazoncognito.com',
  
  // API Gateway Configuration
  api: {
    endpoint: import.meta.env.VITE_API_ENDPOINT || 'https://XXXXX.execute-api.us-east-1.amazonaws.com/prod',
    adminPath: '/admin',
    crawlerPath: '/crawler',
  },
  
  // OAuth URLs
  redirectSignIn: import.meta.env.VITE_REDIRECT_SIGN_IN || 'http://localhost:5173',
  redirectSignOut: import.meta.env.VITE_REDIRECT_SIGN_OUT || 'http://localhost:5173',
  
  // Demo Mode
  demoMode: import.meta.env.VITE_DEMO_MODE === 'true',
};

// Validate configuration
export const validateConfig = (): boolean => {
  const missingVars: string[] = [];
  
  if (config.cognitoUserPoolId.includes('XXXX')) {
    missingVars.push('VITE_USER_POOL_ID');
  }
  
  if (config.cognitoClientId.includes('XXXX')) {
    missingVars.push('VITE_USER_POOL_CLIENT_ID');
  }
  
  if (config.api.endpoint.includes('XXXX')) {
    missingVars.push('VITE_API_ENDPOINT');
  }
  
  if (missingVars.length > 0 && !config.demoMode) {
    console.warn('⚠️ Missing AWS configuration:', missingVars.join(', '));
    console.warn('ℹ️ Set VITE_DEMO_MODE=true to use demo mode');
    return false;
  }
  
  return true;
};

export default config;