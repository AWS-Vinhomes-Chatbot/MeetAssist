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
    if (isNaN(date.getTime())) {
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
        return 'bg-green-100 text-green-800';
      case 'pending':
      case 'upcoming':
        return 'bg-yellow-100 text-yellow-800';
      case 'cancelled':
      case 'inactive':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Header
        title="Overview"
        subtitle="Welcome back! Here's what's happening with your career counseling service."
        actions={
          <Button onClick={fetchData} loading={loading} icon="🔄">
            Refresh
          </Button>
        }
      />

      <div className="p-6">
        {error && (
          <div className="mb-6 rounded-lg bg-red-50 p-4 text-red-700">
            <strong>Error:</strong> {error}
          </div>
        )}

        {/* Stats Grid */}
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
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
          <div className="mt-6">
            <h3 className="mb-4 text-lg font-semibold">Appointment Status Distribution</h3>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              {Object.entries(stats.appointments_by_status).map(([status, count]) => (
                <div key={status} className="rounded-lg border bg-white p-4 shadow-sm">
                  <div className={`inline-block rounded-full px-3 py-1 text-sm font-medium ${getStatusColor(status)}`}>
                    {status}
                  </div>
                  <div className="mt-2 text-2xl font-bold">{count}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recent Data Tables */}
        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Recent Appointments */}
          <div className="rounded-lg border bg-white p-6 shadow-sm">
            <h3 className="mb-4 text-lg font-semibold">Recent Appointments</h3>
            {recentAppointments.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-2 text-left">Customer</th>
                      <th className="px-3 py-2 text-left">Consultant</th>
                      <th className="px-3 py-2 text-left">Date</th>
                      <th className="px-3 py-2 text-left">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentAppointments.map((apt) => (
                      <tr key={apt.appointmentid} className="border-t">
                        <td className="px-3 py-2">{apt.customer_name}</td>
                        <td className="px-3 py-2">{apt.consultant_name}</td>
                        <td className="px-3 py-2">{formatDate(apt.date)}</td>
                        <td className="px-3 py-2">
                          <span className={`inline-block rounded-full px-2 py-1 text-xs ${getStatusColor(apt.status)}`}>
                            {apt.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="flex h-32 items-center justify-center text-gray-500">
                {loading ? 'Loading...' : 'No appointments found'}
              </div>
            )}
          </div>
          
          {/* Community Programs */}
          <div className="rounded-lg border bg-white p-6 shadow-sm">
            <h3 className="mb-4 text-lg font-semibold">Community Programs</h3>
            {programs.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-2 text-left">Program</th>
                      <th className="px-3 py-2 text-left">Date</th>
                      <th className="px-3 py-2 text-left">Participants</th>
                      <th className="px-3 py-2 text-left">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {programs.map((program) => (
                      <tr key={program.programid} className="border-t">
                        <td className="px-3 py-2 font-medium">{program.programname}</td>
                        <td className="px-3 py-2 text-xs">
                          {formatDate(program.date)}
                        </td>
                        <td className="px-3 py-2 text-center">{program.participant_count}</td>
                        <td className="px-3 py-2">
                          <span className={`inline-block rounded-full px-2 py-1 text-xs ${getStatusColor(program.status)}`}>
                            {program.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="flex h-32 items-center justify-center text-gray-500">
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
