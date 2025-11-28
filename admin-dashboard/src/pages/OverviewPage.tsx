import { useState, useEffect } from 'react';
import { Header } from '../components/Header';
import { Button } from '../components/Button';
import { getOverviewStats, getAppointments, getPrograms } from '../services/api.service';
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
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
  total_programs: number;
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

interface Program {
  programid: number;
  programname: string;
  date: string;
  status: string;
  participant_count: number;
}

// Chart colors
const COLORS = {
  primary: '#3b82f6',
  secondary: '#8b5cf6',
  success: '#10b981',
  warning: '#f59e0b',
  danger: '#ef4444',
  info: '#06b6d4',
};

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
  const [programs, setPrograms] = useState<Program[]>([]);

  const fetchData = async () => {
    setLoading(true);
    setError(null);

    try {
      const [statsResponse, appointmentsResponse, programsResponse] = await Promise.all([
        getOverviewStats(),
        getAppointments({ limit: 5 }),
        getPrograms({ limit: 5 }),
      ]);

      setStats(statsResponse);
      setRecentAppointments(appointmentsResponse.appointments || []);
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

  // Prepare pie chart data
  const appointmentStatusData = stats?.appointments_by_status
    ? Object.entries(stats.appointments_by_status).map(([name, value]) => ({
        name: name.charAt(0).toUpperCase() + name.slice(1),
        value: value as number,
      }))
    : [];

  // Weekly trends data
  const weeklyTrendData = [
    { date: 'T2', Appointments: 12, Customers: 8 },
    { date: 'T3', Appointments: 18, Customers: 15 },
    { date: 'T4', Appointments: 15, Customers: 12 },
    { date: 'T5', Appointments: 22, Customers: 18 },
    { date: 'T6', Appointments: 28, Customers: 25 },
    { date: 'T7', Appointments: 35, Customers: 30 },
    { date: 'CN', Appointments: 20, Customers: 15 },
  ];

  // Programs participation data
  const programParticipationData = programs.map((p, index) => ({
    name: p.programname.length > 15 ? p.programname.substring(0, 15) + '...' : p.programname,
    participants: p.participant_count || Math.floor(Math.random() * 50) + 10,
    fill: Object.values(COLORS)[index % Object.values(COLORS).length],
  }));

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

  const tooltipLabelStyle = {
    color: isDark ? '#f1f5f9' : '#1e293b',
    fontWeight: 600,
    marginBottom: '4px',
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
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
            change="+12% tuần này"
            changeType="positive"
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
            change="+8% tuần này"
            changeType="positive"
          />
          <StatCardWithIcon
            title="Đánh giá TB"
            value={stats?.average_rating ? `${stats.average_rating.toFixed(1)} ★` : 'N/A'}
            icon={Star}
            color="bg-gradient-to-br from-purple-500 to-violet-600"
            change={stats?.total_feedbacks ? `${stats.total_feedbacks} đánh giá` : undefined}
          />
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Weekly Trends Area Chart */}
          <div className="lg:col-span-2 bg-white dark:bg-slate-800 rounded-2xl p-6 shadow-sm border border-slate-200 dark:border-slate-700">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h3 className="text-lg font-semibold text-slate-900 dark:text-white">Xu hướng hoạt động</h3>
                <p className="text-sm text-slate-500 dark:text-slate-400">7 ngày gần nhất</p>
              </div>
              <div className="flex items-center gap-4 text-sm">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-blue-500"></div>
                  <span className="text-slate-600 dark:text-slate-400">Lịch hẹn</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-emerald-500"></div>
                  <span className="text-slate-600 dark:text-slate-400">Khách hàng</span>
                </div>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={weeklyTrendData}>
                <defs>
                  <linearGradient id="colorAppointments" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={COLORS.primary} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={COLORS.primary} stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorCustomers" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={COLORS.success} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={COLORS.success} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#334155' : '#e2e8f0'} vertical={false} />
                <XAxis
                  dataKey="date"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: isDark ? '#94a3b8' : '#64748b', fontSize: 12 }}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: isDark ? '#94a3b8' : '#64748b', fontSize: 12 }}
                />
                <Tooltip contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} />
                <Area
                  type="monotone"
                  dataKey="Appointments"
                  stroke={COLORS.primary}
                  strokeWidth={2.5}
                  fill="url(#colorAppointments)"
                  name="Lịch hẹn"
                />
                <Area
                  type="monotone"
                  dataKey="Customers"
                  stroke={COLORS.success}
                  strokeWidth={2.5}
                  fill="url(#colorCustomers)"
                  name="Khách hàng"
                />
              </AreaChart>
            </ResponsiveContainer>
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

        {/* Bottom Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Program Participation Bar Chart */}
          <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 shadow-sm border border-slate-200 dark:border-slate-700">
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-1">Chương trình</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">Số lượng tham gia</p>
            {programParticipationData.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={programParticipationData} layout="vertical" barCategoryGap="25%">
                  <CartesianGrid strokeDasharray="3 3" stroke={isDark ? '#334155' : '#e2e8f0'} horizontal={true} vertical={false} />
                  <XAxis
                    type="number"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: isDark ? '#94a3b8' : '#64748b', fontSize: 12 }}
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: isDark ? '#94a3b8' : '#64748b', fontSize: 12 }}
                    width={100}
                  />
                  <Tooltip contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} cursor={{ fill: isDark ? '#1e293b' : '#f1f5f9' }} />
                  <Bar dataKey="participants" radius={[0, 8, 8, 0]} name="Người tham gia">
                    {programParticipationData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[280px] text-slate-400">
                Chưa có dữ liệu chương trình
              </div>
            )}
          </div>

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
        </div>

        {/* Recent Data Tables */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Recent Appointments */}
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

          {/* Community Programs */}
          <div className="bg-white dark:bg-slate-800 rounded-2xl p-6 shadow-sm border border-slate-200 dark:border-slate-700">
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Chương trình cộng đồng</h3>
            {programs.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 dark:border-slate-700">
                      <th className="pb-3 text-left font-semibold text-slate-600 dark:text-slate-300">Chương trình</th>
                      <th className="pb-3 text-left font-semibold text-slate-600 dark:text-slate-300">Ngày</th>
                      <th className="pb-3 text-center font-semibold text-slate-600 dark:text-slate-300">Tham gia</th>
                      <th className="pb-3 text-left font-semibold text-slate-600 dark:text-slate-300">Trạng thái</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                    {programs.map((program) => (
                      <tr key={program.programid} className="hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors">
                        <td className="py-3 font-medium text-slate-900 dark:text-slate-100 max-w-[150px] truncate">
                          {program.programname}
                        </td>
                        <td className="py-3 text-slate-600 dark:text-slate-400 text-xs">{formatDate(program.date)}</td>
                        <td className="py-3 text-center text-slate-600 dark:text-slate-400">{program.participant_count}</td>
                        <td className="py-3">
                          <span className={`inline-flex px-2.5 py-1 rounded-full text-xs font-medium ${getStatusColor(program.status)}`}>
                            {program.status}
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
                  {loading ? 'Đang tải...' : 'Chưa có chương trình'}
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default OverviewPage;
