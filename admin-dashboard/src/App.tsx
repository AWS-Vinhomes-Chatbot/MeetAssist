import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { authService } from './services/auth.service';
import { Sidebar } from './components/Sidebar';
import { config, validateConfig } from './aws-exports';

// Lazy load pages
const OverviewPage = React.lazy(() => import('./pages/OverviewPage'));
const ConversationsPage = React.lazy(() => import('./pages/ConversationsPage'));
const AnalyticsPage = React.lazy(() => import('./pages/AnalyticsPage'));
const CrawlerPage = React.lazy(() => import('./pages/CrawlerPage'));

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [userEmail, setUserEmail] = useState<string>('');
  const [configValid, setConfigValid] = useState<boolean>(true);

  useEffect(() => {
    // Validate configuration
    const valid = validateConfig();
    setConfigValid(valid);

    // Check authentication
    checkAuth();

    // Handle OAuth callback
    const handleCallback = async () => {
      await authService.handleCallback();
      await checkAuth();
    };
    handleCallback();
  }, []);

  const checkAuth = async () => {
    if (config.demoMode) {
      // Demo mode - skip authentication
      setIsAuthenticated(true);
      setUserEmail('demo@admin.com');
      return;
    }

    try {
      const authenticated = authService.isAuthenticated();
      setIsAuthenticated(authenticated);

      if (authenticated) {
        const user = authService.getCurrentUser();
        if (user) {
          setUserEmail(user.email);
        }
      }
    } catch (error) {
      console.error('Auth check failed:', error);
      setIsAuthenticated(false);
    }
  };

  const handleLogin = () => {
    if (config.demoMode) {
      setIsAuthenticated(true);
      setUserEmail('demo@admin.com');
    } else {
      authService.login();
    }
  };

  const handleLogout = async () => {
    if (config.demoMode) {
      setIsAuthenticated(false);
      setUserEmail('');
    } else {
      await authService.logout();
    }
  };

  // Loading state
  if (isAuthenticated === null) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-100">
        <div className="text-center">
          <div className="mb-4 h-12 w-12 animate-spin rounded-full border-4 border-blue-600 border-t-transparent mx-auto"></div>
          <p className="text-gray-600">Loading Dashboard...</p>
        </div>
      </div>
    );
  }

  // Login screen
  if (!isAuthenticated) {
    return (
      <div className="flex h-screen items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100">
        <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-xl">
          {config.demoMode && (
            <div className="mb-4 rounded-lg bg-orange-100 p-3 text-center text-sm font-medium text-orange-800">
              ⚠️ DEMO MODE - No authentication required
            </div>
          )}
          
          {!configValid && !config.demoMode && (
            <div className="mb-4 rounded-lg bg-red-100 p-3 text-center text-sm font-medium text-red-800">
              ⚠️ Missing AWS configuration. Please set environment variables.
            </div>
          )}
          
          <div className="mb-8 text-center">
            <h1 className="text-3xl font-bold text-gray-900">🤖 Chatbot Admin</h1>
            <p className="mt-2 text-gray-600">Manage conversation history and analytics</p>
          </div>
          
          <button
            onClick={handleLogin}
            className="w-full rounded-lg bg-blue-600 px-6 py-3 font-semibold text-white transition-colors hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            <span className="mr-2">🔐</span>
            {config.demoMode ? 'Enter Demo Mode' : 'Login with Cognito'}
          </button>
          
          <p className="mt-4 text-center text-sm text-gray-500">
            Secured by AWS Cognito
          </p>
        </div>
      </div>
    );
  }

  // Main dashboard
  return (
    <BrowserRouter>
      <div className="flex h-screen bg-gray-50">
        <Sidebar userEmail={userEmail} onLogout={handleLogout} />
        
        <main className="flex-1 overflow-auto">
          {config.demoMode && (
            <div className="bg-gradient-to-r from-orange-500 to-red-500 p-2 text-center text-sm font-semibold text-white">
              ⚠️ DEMO MODE - All data is mocked for demonstration purposes
            </div>
          )}
          
          <React.Suspense
            fallback={
              <div className="flex h-full items-center justify-center">
                <div className="text-center">
                  <div className="mb-4 h-12 w-12 animate-spin rounded-full border-4 border-blue-600 border-t-transparent mx-auto"></div>
                  <p className="text-gray-600">Loading...</p>
                </div>
              </div>
            }
          >
            <Routes>
              <Route path="/" element={<OverviewPage />} />
              <Route path="/conversations" element={<ConversationsPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
              <Route path="/crawler" element={<CrawlerPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </React.Suspense>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
