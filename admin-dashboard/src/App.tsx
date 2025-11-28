import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { authService } from './services/auth.service';
import { Sidebar } from './components/Sidebar';
import { config, validateConfig } from './aws-exports';

// Lazy load pages
const OverviewPage = React.lazy(() => import('./pages/OverviewPage'));
const ConversationsPage = React.lazy(() => import('./pages/ConversationsPage'));
const AnalyticsPage = React.lazy(() => import('./pages/AnalyticsPage'));
const ConsultantsPage = React.lazy(() => import('./pages/ConsultantsPage'));
const AppointmentsPage = React.lazy(() => import('./pages/AppointmentsPage'));
const ProgramsPage = React.lazy(() => import('./pages/ProgramsPage'));

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [userEmail, setUserEmail] = useState<string>('');
  const [configValid, setConfigValid] = useState<boolean>(true);

  useEffect(() => {
    // Validate configuration
    const valid = validateConfig();
    setConfigValid(valid);

    // Handle OAuth callback first
    const handleCallback = async () => {
      if (globalThis.location.pathname === '/callback') {
        try {
          await authService.handleCallback();
        } catch (error) {
          console.error('Callback error:', error);
          alert('Login failed: ' + (error instanceof Error ? error.message : 'Unknown error'));
        }
      }
      // Then check authentication
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
      <div className="flex h-screen items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="text-center">
          <div className="mb-4 h-12 w-12 animate-spin rounded-full border-4 border-primary-600 border-t-transparent mx-auto"></div>
          <p className="text-gray-600 dark:text-gray-400">Loading Dashboard...</p>
        </div>
      </div>
    );
  }

  // Login screen
  if (!isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800 p-4">
        <div className="w-full max-w-md rounded-2xl bg-white dark:bg-gray-800 p-8 shadow-xl border border-gray-200 dark:border-gray-700">
          {config.demoMode && (
            <div className="mb-4 rounded-lg bg-orange-100 dark:bg-orange-900/30 p-3 text-center text-sm font-medium text-orange-800 dark:text-orange-300">
              ⚠️ DEMO MODE - No authentication required
            </div>
          )}
          
          {!configValid && !config.demoMode && (
            <div className="mb-4 rounded-lg bg-red-100 dark:bg-red-900/30 p-3 text-center text-sm font-medium text-red-800 dark:text-red-300">
              ⚠️ Missing AWS configuration. Please set environment variables.
            </div>
          )}
          
          <div className="mb-8 text-center">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary-100 dark:bg-primary-900/30 mb-4">
              <span className="text-3xl">🤖</span>
            </div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Chatbot Admin</h1>
            <p className="mt-2 text-gray-600 dark:text-gray-400">Manage conversation history and analytics</p>
          </div>
          
          <button
            onClick={handleLogin}
            className="w-full rounded-lg bg-primary-600 px-6 py-3 font-semibold text-white transition-all hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800 active:scale-[0.98]"
          >
            <span className="mr-2">🔐</span>
            {config.demoMode ? 'Enter Demo Mode' : 'Login with Cognito'}
          </button>
          
          <p className="mt-4 text-center text-sm text-gray-500 dark:text-gray-400">
            Secured by AWS Cognito
          </p>
        </div>
      </div>
    );
  }

  // Main dashboard
  return (
    <BrowserRouter>
      <div className="flex min-h-screen bg-gray-50 dark:bg-gray-900">
        <Sidebar userEmail={userEmail} onLogout={handleLogout} />
        
        <main className="flex-1 lg:ml-0 overflow-auto">
          {config.demoMode && (
            <div className="bg-gradient-to-r from-orange-500 to-red-500 px-4 py-2 text-center text-sm font-medium text-white">
              ⚠️ DEMO MODE - All data is mocked for demonstration purposes
            </div>
          )}
          
          <React.Suspense
            fallback={
              <div className="flex h-full items-center justify-center min-h-[50vh]">
                <div className="text-center">
                  <div className="mb-4 h-10 w-10 animate-spin rounded-full border-4 border-primary-600 border-t-transparent mx-auto"></div>
                  <p className="text-gray-600 dark:text-gray-400">Loading...</p>
                </div>
              </div>
            }
          >
            <Routes>
              <Route path="/" element={<OverviewPage />} />
              <Route path="/conversations" element={<ConversationsPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
              <Route path="/consultants" element={<ConsultantsPage />} />
              <Route path="/appointments" element={<AppointmentsPage />} />
              <Route path="/programs" element={<ProgramsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </React.Suspense>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
