import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, NavLink } from 'react-router-dom';
import { authService, ConsultantInfo } from './services/auth.service';
import { apiService } from './services/api.service';
import { config, validateConfig, loadConfig } from './aws-exports';
import { LogIn, Loader2, AlertTriangle, Calendar, CalendarCheck, LogOut, User } from 'lucide-react';
import SchedulePage from './pages/SchedulePage';
import AppointmentsPage from './pages/AppointmentsPage';

interface ConsultantData {
  consultantid: number;
  fullname: string;
  email: string;
  specialties?: string;
}

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [consultantInfo, setConsultantInfo] = useState<ConsultantInfo | null>(null);
  const [consultantData, setConsultantData] = useState<ConsultantData | null>(null);
  const [configValid, setConfigValid] = useState<boolean>(true);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const initApp = async () => {
      try {
        await loadConfig();
        const valid = validateConfig();
        setConfigValid(valid);

        if (globalThis.location.pathname === '/callback') {
          try {
            await authService.handleCallback();
          } catch (err) {
            console.error('Callback error:', err);
            setError('Login failed: ' + (err instanceof Error ? err.message : 'Unknown error'));
          }
        }

        await checkAuth();
      } finally {
        setIsLoading(false);
      }
    };

    initApp();
  }, []);

  const checkAuth = async () => {
    try {
      const authenticated = await authService.isAuthenticated();
      setIsAuthenticated(authenticated);

      if (authenticated) {
        const info = await authService.getConsultantInfo();
        setConsultantInfo(info);

        if (info?.email) {
          try {
            const data = await apiService.getConsultantByEmail(info.email);
            setConsultantData(data);
          } catch (err) {
            console.error('Failed to get consultant data:', err);
            setError('Consultant not found. Please contact admin.');
          }
        }
      }
    } catch (err) {
      console.error('Auth check failed:', err);
      setIsAuthenticated(false);
    }
  };

  const handleLogin = async () => {
    await authService.login();
  };

  const handleLogout = async () => {
    await authService.logout();
    setIsAuthenticated(false);
    setConsultantInfo(null);
    setConsultantData(null);
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="w-12 h-12 animate-spin text-teal-500 mx-auto mb-4" />
          <p className="text-gray-600">Loading...</p>
        </div>
      </div>
    );
  }

  if (!configValid && !config.demoMode) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center max-w-md">
          <AlertTriangle className="w-16 h-16 text-yellow-500 mx-auto mb-4" />
          <h1 className="text-xl font-semibold text-gray-800 mb-2">Configuration Error</h1>
          <p className="text-gray-600">Unable to load configuration. Please contact admin.</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-teal-50 to-cyan-100 flex items-center justify-center">
        <div className="bg-white rounded-2xl shadow-xl p-8 max-w-md w-full mx-4">
          <div className="text-center mb-8">
            <Calendar className="w-16 h-16 text-teal-500 mx-auto mb-4" />
            <h1 className="text-2xl font-bold text-gray-800">Consultant Portal</h1>
            <p className="text-gray-600 mt-2">View your schedule and manage appointments</p>
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
              <p className="text-red-700 text-sm">{error}</p>
            </div>
          )}

          <button
            onClick={handleLogin}
            className="w-full flex items-center justify-center gap-2 bg-teal-500 hover:bg-teal-600 text-white font-semibold py-3 px-6 rounded-lg transition-colors"
          >
            <LogIn className="w-5 h-5" />
            Sign In
          </button>

          {config.demoMode && (
            <p className="text-center text-gray-400 text-sm mt-4">Demo Mode Active</p>
          )}
        </div>
      </div>
    );
  }

  if (error && !consultantData) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center max-w-md bg-white p-8 rounded-lg shadow">
          <AlertTriangle className="w-16 h-16 text-red-500 mx-auto mb-4" />
          <h1 className="text-xl font-semibold text-gray-800 mb-2">Access Denied</h1>
          <p className="text-gray-600 mb-4">{error}</p>
          <button onClick={handleLogout} className="text-teal-500 hover:text-teal-600">
            Sign out and try again
          </button>
        </div>
      </div>
    );
  }

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50">
        {/* Header */}
        <header className="bg-white shadow-sm border-b">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between items-center h-16">
              <div className="flex items-center gap-3">
                <Calendar className="w-8 h-8 text-teal-500" />
                <h1 className="text-xl font-semibold text-gray-800">Consultant Portal</h1>
              </div>

              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2 text-gray-600">
                  <User className="w-5 h-5" />
                  <span>{consultantData?.fullname || consultantInfo?.email}</span>
                </div>
                <button
                  onClick={handleLogout}
                  className="flex items-center gap-1 text-gray-500 hover:text-red-500 transition-colors"
                  title="Sign out"
                >
                  <LogOut className="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>
        </header>

        {/* Navigation */}
        <nav className="bg-white border-b">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex gap-8">
              <NavLink 
                to="/" 
                end
                className={({ isActive }) => 
                  `flex items-center gap-2 py-4 border-b-2 transition-colors ${
                    isActive 
                      ? 'border-teal-500 text-teal-600' 
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`
                }
              >
                <Calendar className="w-5 h-5" />
                <span className="font-medium">My Schedule</span>
              </NavLink>
              <NavLink 
                to="/appointments"
                className={({ isActive }) => 
                  `flex items-center gap-2 py-4 border-b-2 transition-colors ${
                    isActive 
                      ? 'border-teal-500 text-teal-600' 
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`
                }
              >
                <CalendarCheck className="w-5 h-5" />
                <span className="font-medium">Appointments</span>
              </NavLink>
            </div>
          </div>
        </nav>

        {/* Main Content */}
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <Routes>
            <Route path="/" element={<SchedulePage consultantId={consultantData?.consultantid || 0} />} />
            <Route path="/appointments" element={<AppointmentsPage consultantId={consultantData?.consultantid || 0} />} />
            <Route path="/callback" element={<Navigate to="/" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
