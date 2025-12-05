import { useState, useEffect } from 'react';
import { apiService } from '../services/api.service';
import { CalendarCheck, Clock, Loader2, User, Phone, Mail, Check, X, RefreshCw, Filter } from 'lucide-react';
import { format, parseISO } from 'date-fns';

interface Appointment {
  appointmentid: number;
  date: string;
  time: string;
  duration: number;
  status: string;
  description: string;
  customer_name: string;
  customer_email: string;
  customer_phone: string;
}

type StatusFilter = 'all' | 'pending' | 'confirmed' | 'completed' | 'cancelled';

interface Props {
  consultantId: number;
}

export default function AppointmentsPage({ consultantId }: Props) {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  useEffect(() => {
    if (consultantId) {
      loadAppointments();
    }
  }, [consultantId, statusFilter]);

  const loadAppointments = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiService.getMyAppointments(consultantId, {
        status: statusFilter === 'all' ? undefined : statusFilter,
        limit: 100
      });
      setAppointments(data.appointments);
    } catch (err) {
      console.error('Failed to load appointments:', err);
      setError('Failed to load appointments');
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirm = async (appointmentId: number) => {
    setActionLoading(appointmentId);
    try {
      const result = await apiService.confirmAppointment(consultantId, appointmentId);
      if (result.success) {
        loadAppointments();
      } else {
        alert(result.error || 'Failed to confirm appointment');
      }
    } catch (err) {
      console.error('Failed to confirm:', err);
      alert('Failed to confirm appointment');
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeny = async (appointmentId: number) => {
    const reason = prompt('Reason for cancellation (optional):');
    setActionLoading(appointmentId);
    try {
      const result = await apiService.denyAppointment(consultantId, appointmentId, reason || undefined);
      if (result.success) {
        loadAppointments();
      } else {
        alert(result.error || 'Failed to cancel appointment');
      }
    } catch (err) {
      console.error('Failed to deny:', err);
      alert('Failed to cancel appointment');
    } finally {
      setActionLoading(null);
    }
  };

  const getStatusBadge = (status: string) => {
    const styles: Record<string, string> = {
      pending: 'bg-yellow-100 text-yellow-700 border-yellow-200',
      confirmed: 'bg-green-100 text-green-700 border-green-200',
      completed: 'bg-blue-100 text-blue-700 border-blue-200',
      cancelled: 'bg-red-100 text-red-700 border-red-200'
    };
    return (
      <span className={`px-3 py-1 rounded-full text-sm font-medium border ${styles[status] || 'bg-gray-100 text-gray-700'}`}>
        {status.charAt(0).toUpperCase() + status.slice(1)}
      </span>
    );
  };

  const statusCounts = appointments.reduce((acc, apt) => {
    acc[apt.status] = (acc[apt.status] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const renderContent = () => {
    if (isLoading) {
      return (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-8 h-8 animate-spin text-teal-500" />
        </div>
      );
    }

    if (error) {
      return (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
          <p className="text-red-600">{error}</p>
          <button onClick={loadAppointments} className="mt-4 text-teal-500 hover:underline">
            Try again
          </button>
        </div>
      );
    }

    if (appointments.length === 0) {
      return (
        <div className="bg-white rounded-lg shadow p-12 text-center">
          <CalendarCheck className="w-16 h-16 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-gray-700">No appointments found</h3>
          <p className="text-gray-500 mt-2">
            {statusFilter === 'all' ? 'You have no appointments yet' : `No ${statusFilter} appointments`}
          </p>
        </div>
      );
    }

    return (
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">Date & Time</th>
                <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">Customer</th>
                <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">Duration</th>
                <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">Status</th>
                <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {appointments.map((apt) => (
                <tr key={apt.appointmentid} className="hover:bg-gray-50">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-teal-100 rounded-lg flex items-center justify-center">
                        <CalendarCheck className="w-5 h-5 text-teal-500" />
                      </div>
                      <div>
                        <p className="font-medium text-gray-800">
                          {format(parseISO(apt.date), 'EEEE, MMMM d')}
                        </p>
                        <p className="text-sm text-gray-500 flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {apt.time}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div>
                      <p className="font-medium text-gray-800 flex items-center gap-2">
                        <User className="w-4 h-4 text-gray-400" />
                        {apt.customer_name}
                      </p>
                      <p className="text-sm text-gray-500 flex items-center gap-1">
                        <Mail className="w-3 h-3" />
                        {apt.customer_email}
                      </p>
                      {apt.customer_phone && (
                        <p className="text-sm text-gray-500 flex items-center gap-1">
                          <Phone className="w-3 h-3" />
                          {apt.customer_phone}
                        </p>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-gray-700">{apt.duration} mins</span>
                  </td>
                  <td className="px-6 py-4">
                    {getStatusBadge(apt.status)}
                  </td>
                  <td className="px-6 py-4">
                    {apt.status === 'pending' && (
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleConfirm(apt.appointmentid)}
                          disabled={actionLoading === apt.appointmentid}
                          className="flex items-center gap-1 px-3 py-1.5 bg-green-500 hover:bg-green-600 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                        >
                          {actionLoading === apt.appointmentid ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <Check className="w-4 h-4" />
                          )}
                          Confirm
                        </button>
                        <button
                          onClick={() => handleDeny(apt.appointmentid)}
                          disabled={actionLoading === apt.appointmentid}
                          className="flex items-center gap-1 px-3 py-1.5 bg-red-500 hover:bg-red-600 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                        >
                          <X className="w-4 h-4" />
                          Deny
                        </button>
                      </div>
                    )}
                    {apt.status === 'confirmed' && (
                      <button
                        onClick={() => handleDeny(apt.appointmentid)}
                        disabled={actionLoading === apt.appointmentid}
                        className="flex items-center gap-1 px-3 py-1.5 border border-red-300 text-red-600 hover:bg-red-50 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                      >
                        <X className="w-4 h-4" />
                        Cancel
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-2xl font-bold text-gray-800">Appointments</h2>
          <p className="text-gray-500 mt-1">Manage your appointments</p>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-gray-500" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
            >
              <option value="all">All Status</option>
              <option value="pending">Pending ({statusCounts.pending || 0})</option>
              <option value="confirmed">Confirmed ({statusCounts.confirmed || 0})</option>
              <option value="completed">Completed ({statusCounts.completed || 0})</option>
              <option value="cancelled">Cancelled ({statusCounts.cancelled || 0})</option>
            </select>
          </div>

          <button
            onClick={loadAppointments}
            className="flex items-center gap-2 px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Pending" count={statusCounts.pending || 0} color="yellow" />
        <StatCard label="Confirmed" count={statusCounts.confirmed || 0} color="green" />
        <StatCard label="Completed" count={statusCounts.completed || 0} color="blue" />
        <StatCard label="Cancelled" count={statusCounts.cancelled || 0} color="red" />
      </div>

      {/* Content */}
      {renderContent()}
    </div>
  );
}

function StatCard({ label, count, color }: { label: string; count: number; color: string }) {
  const colors: Record<string, string> = {
    yellow: 'bg-yellow-50 text-yellow-700 border-yellow-200',
    green: 'bg-green-50 text-green-700 border-green-200',
    blue: 'bg-blue-50 text-blue-700 border-blue-200',
    red: 'bg-red-50 text-red-700 border-red-200'
  };

  return (
    <div className={`${colors[color]} border rounded-lg p-4`}>
      <p className="text-2xl font-bold">{count}</p>
      <p className="text-sm">{label}</p>
    </div>
  );
}

