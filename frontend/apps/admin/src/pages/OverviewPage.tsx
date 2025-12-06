import { useState, useEffect } from 'react';
import { Header } from '../components/Header';
import { Button } from '../components/Button';
import { getOverviewStats, getAppointments } from '../services/api.service';
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import {
  Users,
  UserCheck,
  CalendarCheck,
  Star,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  CheckCircle,
  Clock,
  XCircle,
} from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';

interface OverviewStats {
  total_customers: number;
  total_consultants: number;
  total_appointments: number;
  appointments_by_status: Record<string, number>;
  average_rating: number;
  total_feedbacks: number;
}

// Helper function to format date from PostgreSQL
const formatDate = (dateStr: string): string => {
  if (!dateStr) return 'N/A';
  try {
    const date = new Date(dateStr);
    if (Number.isNaN(date.getTime())) {
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
  date: string;
  time: string;
  status: string;
}

// Chart colors
const PIE_COLORS = ['#10b981', '#f59e0b', '#ef4444', '#3b82f6', '#8b5cf6', '#06b6d4'];

// Stat card with icon
const StatCardWithIcon = ({
  title,
  value,
  icon: Icon,
  color,
  change,
  changeType = 'neutral',
}: {
  title: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
}) => (
  <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 shadow-sm border border-slate-200 dark:border-slate-700 hover:shadow-md transition-all">
    <div className="flex items-start justify-between">
      <div className="flex-1">
        <p className="text-sm font-medium text-slate-500 dark:text-slate-400">{title}</p>
        <p className="mt-2 text-3xl font-bold text-slate-900 dark:text-white">{value}</p>
        {change && (
          <div className={`flex items-center mt-2 text-sm ${
            changeType === 'positive' ? 'text-emerald-600 dark:text-emerald-400' :
            changeType === 'negative' ? 'text-rose-600 dark:text-rose-400' :
            'text-slate-500 dark:text-slate-400'
          }`}>
            {changeType === 'positive' && <TrendingUp className="w-4 h-4 mr-1" />}
            {changeType === 'negative' && <TrendingDown className="w-4 h-4 mr-1" />}
            <span>{change}</span>
          </div>
        )}
      </div>
      <div className={`p-3 rounded-xl ${color} shadow-lg`}>
        <Icon size={24} className="text-white" />
      </div>
    </div>
  </div>
);

const OverviewPage: React.FC = () => {
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [recentAppointments, setRecentAppointments] = useState<Appointment[]>([]);

  const fetchData = async () => {
    setLoading(true);
    setError(null);

    try {
      const [statsResponse, appointmentsResponse] = await Promise.all([
        getOverviewStats(),
        getAppointments({ limit: 5 }),
      ]);

      setStats(statsResponse);
      setRecentAppointments(appointmentsResponse.appointments || []);
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

  // Prepare pie chart data
  const appointmentStatusData = stats?.appointments_by_status
    ? Object.entries(stats.appointments_by_status).map(([name, value]) => ({
        name: name.charAt(0).toUpperCase() + name.slice(1),
        value: value as number,
      }))
    : [];

  const getStatusColor = (status: string) => {
    switch (status?.toLowerCase()) {
      case 'confirmed':
      case 'completed':
      case 'active':
        return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400';
      case 'pending':
      case 'upcoming':
        return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400';
      case 'cancelled':
      case 'inactive':
        return 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-400';
      default:
        return 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300';
    }
  };

  const totalAppointments = stats?.total_appointments || 0;
  const completedCount = stats?.appointments_by_status?.['completed'] || stats?.appointments_by_status?.['Completed'] || 0;
  const pendingCount = stats?.appointments_by_status?.['pending'] || stats?.appointments_by_status?.['Pending'] || 0;
  const cancelledCount = stats?.appointments_by_status?.['cancelled'] || stats?.appointments_by_status?.['Cancelled'] || 0;
  const completionRate = totalAppointments > 0 ? Math.round((completedCount / totalAppointments) * 100) : 0;

  // Tooltip styles
  const tooltipStyle = {
    backgroundColor: isDark ? '#1e293b' : '#ffffff',
    border: `1px solid ${isDark ? '#334155' : '#e2e8f0'}`,
    borderRadius: '12px',
    boxShadow: '0 10px 40px -10px rgba(0, 0, 0, 0.2)',
    padding: '12px 16px',
  };

  return (
    <div className="flex-1 bg-slate-50 dark:bg-slate-900">
      <Header
        title="Dashboard Overview"
        subtitle="Tổng quan hoạt động hệ thống MeetAssist"
        actions={
          <Button onClick={fetchData} loading={loading} variant="secondary">
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            <span className="ml-2">Làm mới</span>
          </Button>
        }
      />

      <div className="p-4 sm:p-6 space-y-6">
        {error && (
          <div className="bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-800 rounded-xl p-4">
            <p className="text-rose-700 dark:text-rose-300">
              <strong>Lỗi:</strong> {error}
            </p>
          </div>
        )}

        {/* Stats Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
          <StatCardWithIcon
            title="Tổng khách hàng"
            value={stats?.total_customers || 0}
            icon={Users}
            color="bg-gradient-to-br from-blue-500 to-blue-600"
          />
          <StatCardWithIcon
            title="Tư vấn viên"
            value={stats?.total_consultants || 0}
            icon={UserCheck}
            color="bg-gradient-to-br from-emerald-500 to-emerald-600"
          />
          <StatCardWithIcon
            title="Lịch hẹn"
            value={stats?.total_appointments || 0}
            icon={CalendarCheck}
            color="bg-gradient-to-br from-amber-500 to-orange-500"
          />
          <StatCardWithIcon
            title="Đánh giá TB"
            value={stats?.average_rating ? `${stats.average_rating.toFixed(1)} ★` : 'N/A'}
            icon={Star}
            color="bg-gradient-to-br from-purple-500 to-violet-600"
            change={stats?.total_feedbacks ? `${stats.total_feedbacks} đánh giá` : undefined}
          />
        </div>

        {/* Charts Row - Quick Stats on left, Pie Chart on right */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Quick Stats */}
          <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 shadow-sm border border-slate-200 dark:border-slate-700">
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-6">Thống kê nhanh</h3>
            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-700/50 rounded-xl">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-emerald-100 dark:bg-emerald-900/30 rounded-xl">
                    <CheckCircle className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                  </div>
                  <div>
                    <p className="font-medium text-slate-900 dark:text-white">Hoàn thành</p>
                    <p className="text-sm text-slate-500 dark:text-slate-400">Tỷ lệ: {completionRate}%</p>
                  </div>
                </div>
                <span className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">{completedCount}</span>
              </div>

              <div className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-700/50 rounded-xl">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-amber-100 dark:bg-amber-900/30 rounded-xl">
                    <Clock className="w-5 h-5 text-amber-600 dark:text-amber-400" />
                  </div>
                  <div>
                    <p className="font-medium text-slate-900 dark:text-white">Đang chờ</p>
                    <p className="text-sm text-slate-500 dark:text-slate-400">Cần xử lý</p>
                  </div>
                </div>
                <span className="text-2xl font-bold text-amber-600 dark:text-amber-400">{pendingCount}</span>
              </div>

              <div className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-700/50 rounded-xl">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-rose-100 dark:bg-rose-900/30 rounded-xl">
                    <XCircle className="w-5 h-5 text-rose-600 dark:text-rose-400" />
                  </div>
                  <div>
                    <p className="font-medium text-slate-900 dark:text-white">Đã hủy</p>
                    <p className="text-sm text-slate-500 dark:text-slate-400">Lịch hẹn bị hủy</p>
                  </div>
                </div>
                <span className="text-2xl font-bold text-rose-600 dark:text-rose-400">{cancelledCount}</span>
              </div>

              {/* Progress bar */}
              <div className="pt-2">
                <div className="flex justify-between text-sm mb-2">
                  <span className="text-slate-600 dark:text-slate-400">Tỷ lệ hoàn thành</span>
                  <span className="font-semibold text-slate-900 dark:text-white">{completionRate}%</span>
                </div>
                <div className="h-3 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-full transition-all duration-500"
                    style={{ width: `${completionRate}%` }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Appointment Status Pie Chart */}
          <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 shadow-sm border border-slate-200 dark:border-slate-700">
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-1">Trạng thái lịch hẹn</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">Phân bố theo trạng thái</p>
            {appointmentStatusData.length > 0 ? (
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie
                    data={appointmentStatusData}
                    cx="50%"
                    cy="45%"
                    innerRadius={55}
                    outerRadius={85}
                    paddingAngle={4}
                    dataKey="value"
                  >
                    {appointmentStatusData.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend
                    verticalAlign="bottom"
                    height={36}
                    formatter={(value) => (
                      <span className="text-slate-600 dark:text-slate-400 text-sm">{value}</span>
                    )}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[260px] text-slate-400">
                Chưa có dữ liệu
              </div>
            )}
          </div>
        </div>

        {/* Recent Appointments - Full Width */}
        <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 shadow-sm border border-slate-200 dark:border-slate-700">
          <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Lịch hẹn gần đây</h3>
          {recentAppointments.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-700">
                    <th className="pb-3 text-left font-semibold text-slate-600 dark:text-slate-300">Khách hàng</th>
                    <th className="pb-3 text-left font-semibold text-slate-600 dark:text-slate-300">Tư vấn viên</th>
                    <th className="pb-3 text-left font-semibold text-slate-600 dark:text-slate-300">Ngày</th>
                    <th className="pb-3 text-left font-semibold text-slate-600 dark:text-slate-300">Trạng thái</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                  {recentAppointments.map((apt) => (
                    <tr key={apt.appointmentid} className="hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors">
                      <td className="py-3 text-slate-900 dark:text-slate-100 font-medium">{apt.customer_name}</td>
                      <td className="py-3 text-slate-600 dark:text-slate-400">{apt.consultant_name}</td>
                      <td className="py-3 text-slate-600 dark:text-slate-400">{formatDate(apt.date)}</td>
                      <td className="py-3">
                        <span className={`inline-flex px-2.5 py-1 rounded-full text-xs font-medium ${getStatusColor(apt.status)}`}>
                          {apt.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="flex h-32 items-center justify-center">
              <p className="text-slate-500 dark:text-slate-400">
                {loading ? 'Đang tải...' : 'Chưa có lịch hẹn'}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default OverviewPage;
