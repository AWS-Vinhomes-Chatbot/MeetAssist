import { useState, useEffect } from 'react';
import { Header } from '../components/Header';
import { StatCard } from '../components/Card';
import { Button } from '../components/Button';
import { getOverviewStats, getAppointments, getPrograms } from '../services/api.service';

interface OverviewStats {
  total_customers: number;
  total_consultants: number;
  total_appointments: number;
  total_programs: number;
  appointments_by_status: Record<string, number>;
  average_rating: number;
  total_feedbacks: number;
}

// Helper function to format date from PostgreSQL
const formatDate = (dateStr: string): string => {
  if (!dateStr) return 'N/A';
  try {
    // PostgreSQL date format: YYYY-MM-DD or with timestamp
    const date = new Date(dateStr);
    if (Number.isNaN(date.getTime())) {
      // Try parsing as DD/MM/YYYY or other formats
      return dateStr.split('T')[0] || dateStr;
    }
    return date.toLocaleDateString('vi-VN');
  } catch {
    return dateStr;
  }
};

interface Appointment {
  appointmentid: number;
  customer_name: string;
  consultant_name: string;
  date: string;  // Backend returns 'date' field
  time: string;  // Backend returns 'time' field
  status: string;
}

interface Program {
  programid: number;
  programname: string;
  date: string;  // Backend returns single 'date' field
  status: string;
  participant_count: number;
}

const OverviewPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [recentAppointments, setRecentAppointments] = useState<Appointment[]>([]);
  const [programs, setPrograms] = useState<Program[]>([]);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const [statsResponse, appointmentsResponse, programsResponse] = await Promise.all([
        getOverviewStats(),
        getAppointments({ limit: 5 }),
        getPrograms({ limit: 5 })
      ]);
      
      console.log('Stats response:', statsResponse);
      console.log('Appointments response:', appointmentsResponse);
      console.log('Programs response:', programsResponse);
      
      // Stats data is directly in response (not in response.data)
      setStats(statsResponse);
      // Appointments are in response.appointments array
      setRecentAppointments(appointmentsResponse.appointments || []);
      // Programs are in response.programs array
      setPrograms(programsResponse.programs || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
      console.error('Error fetching overview data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const getStatusColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'confirmed':
      case 'completed':
      case 'active':
        return 'badge-success';
      case 'pending':
      case 'upcoming':
        return 'badge-warning';
      case 'cancelled':
      case 'inactive':
        return 'badge-error';
      default:
        return 'badge-neutral';
    }
  };

  return (
    <div className="min-h-screen">
      <Header
        title="Overview"
        subtitle="Welcome back! Here's what's happening with your career counseling service."
        actions={
          <Button onClick={fetchData} loading={loading} icon="🔄">
            Refresh
          </Button>
        }
      />

      <div className="p-4 sm:p-6 space-y-6">
        {error && (
          <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-4 text-red-700 dark:text-red-300">
            <strong>Error:</strong> {error}
          </div>
        )}

        {/* Stats Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
          <StatCard
            title="Total Customers"
            value={stats?.total_customers?.toString() || '0'}
            icon="👥"
            color="blue"
          />
          <StatCard
            title="Consultants"
            value={stats?.total_consultants?.toString() || '0'}
            icon="👨‍💼"
            color="green"
          />
          <StatCard
            title="Appointments"
            value={stats?.total_appointments?.toString() || '0'}
            icon="📅"
            color="orange"
          />
          <StatCard
            title="Avg Rating"
            value={stats?.average_rating ? `${stats.average_rating.toFixed(1)} ⭐` : 'N/A'}
            icon="⭐"
            change={stats?.total_feedbacks ? `${stats.total_feedbacks} feedbacks` : undefined}
            color="purple"
          />
        </div>

        {/* Appointment Status Distribution */}
        {stats?.appointments_by_status && (
          <div>
            <h3 className="mb-4 text-lg font-semibold text-gray-900 dark:text-white">Appointment Status Distribution</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {Object.entries(stats.appointments_by_status).map(([status, count]) => (
                <div key={status} className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 transition-all hover:shadow-md">
                  <span className={`badge ${getStatusColor(status)}`}>
                    {status}
                  </span>
                  <div className="mt-3 text-2xl font-bold text-gray-900 dark:text-white">{count}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recent Data Tables */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          {/* Recent Appointments */}
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Recent Appointments</h3>
            </div>
            {recentAppointments.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 dark:bg-gray-800/50">
                      <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">Customer</th>
                      <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">Consultant</th>
                      <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">Date</th>
                      <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                    {recentAppointments.map((apt) => (
                      <tr key={apt.appointmentid} className="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                        <td className="px-4 py-3 text-gray-900 dark:text-gray-100">{apt.customer_name}</td>
                        <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{apt.consultant_name}</td>
                        <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{formatDate(apt.date)}</td>
                        <td className="px-4 py-3">
                          <span className={`badge ${getStatusColor(apt.status)}`}>
                            {apt.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="flex h-32 items-center justify-center text-gray-500 dark:text-gray-400">
                {loading ? 'Loading...' : 'No appointments found'}
              </div>
            )}
          </div>
          
          {/* Community Programs */}
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Community Programs</h3>
            </div>
            {programs.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 dark:bg-gray-800/50">
                      <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">Program</th>
                      <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">Date</th>
                      <th className="px-4 py-3 text-center font-semibold text-gray-600 dark:text-gray-300">Participants</th>
                      <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                    {programs.map((program) => (
                      <tr key={program.programid} className="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                        <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">{program.programname}</td>
                        <td className="px-4 py-3 text-gray-600 dark:text-gray-400 text-xs">
                          {formatDate(program.date)}
                        </td>
                        <td className="px-4 py-3 text-center text-gray-600 dark:text-gray-400">{program.participant_count}</td>
                        <td className="px-4 py-3">
                          <span className={`badge ${getStatusColor(program.status)}`}>
                            {program.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="flex h-32 items-center justify-center text-gray-500 dark:text-gray-400">
                {loading ? 'Loading...' : 'No programs found'}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default OverviewPage;
