import { useState, useEffect } from 'react';
import { apiService } from '../services/api.service';
import { CalendarCheck, Clock, Loader2, User, Phone, Mail, Check, X, RefreshCw, Filter, CheckCircle, AlertCircle } from 'lucide-react';
import { formatDateVN, formatTimeVN, statusToVietnamese, getStatusBadgeClass } from '../utils/formatters';

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

type ModalType = 'confirm' | 'cancel' | 'complete' | 'error' | null;

interface ModalState {
  type: ModalType;
  appointmentId: number | null;
  title: string;
  message: string;
  cancelReason?: string;
}

interface Props {
  consultantId: number;
}

export default function AppointmentsPage({ consultantId }: Props) {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [modalState, setModalState] = useState<ModalState>({
    type: null,
    appointmentId: null,
    title: '',
    message: '',
    cancelReason: ''
  });

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
      setError('Không thể tải danh sách cuộc hẹn');
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirm = (appointmentId: number) => {
    setModalState({
      type: 'confirm',
      appointmentId,
      title: 'Xác Nhận Cuộc Hẹn',
      message: 'Bạn có chắc chắn muốn xác nhận cuộc hẹn này? Khách hàng sẽ nhận được thông báo qua email.'
    });
  };

  const confirmAppointment = async () => {
    if (!modalState.appointmentId) return;
    setActionLoading(modalState.appointmentId);
    setModalState({ type: null, appointmentId: null, title: '', message: '' });
    try {
      const result = await apiService.confirmAppointment(consultantId, modalState.appointmentId);
      if (result.success) {
        // Auto-send confirmation email to customer
        if (result.customer_email && result.customer_name && result.consultant_name) {
          try {
            await apiService.sendConfirmationEmail({
              appointment_id: modalState.appointmentId,
              customer_email: result.customer_email,
              customer_name: result.customer_name,
              consultant_name: result.consultant_name,
              date: result.date || '',
              time: result.time || '',
              duration: result.duration,
              meeting_url: result.meeting_url,
              description: result.description
            });
            console.log('Confirmation email sent successfully');
          } catch (emailErr) {
            // Email sending failed but appointment is already confirmed
            console.error('Failed to send confirmation email:', emailErr);
            // Don't show error to user - appointment is confirmed successfully
          }
        }
        loadAppointments();
      } else {
        setModalState({
          type: 'error',
          appointmentId: null,
          title: 'Lỗi',
          message: result.error || 'Không thể xác nhận cuộc hẹn'
        });
      }
    } catch (err) {
      console.error('Failed to confirm:', err);
      setModalState({
        type: 'error',
        appointmentId: null,
        title: 'Lỗi',
        message: 'Không thể xác nhận cuộc hẹn'
      });
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeny = (appointmentId: number) => {
    setModalState({
      type: 'cancel',
      appointmentId,
      title: 'Hủy Cuộc Hẹn',
      message: 'Bạn có chắc chắn muốn hủy cuộc hẹn này? Khách hàng sẽ nhận được thông báo qua email.',
      cancelReason: ''
    });
  };

  const cancelAppointment = async () => {
    if (!modalState.appointmentId) return;
    setActionLoading(modalState.appointmentId);
    const appointmentId = modalState.appointmentId;
    const reason = modalState.cancelReason;
    setModalState({ type: null, appointmentId: null, title: '', message: '' });
    try {
      const result = await apiService.denyAppointment(consultantId, appointmentId, reason || undefined);
      if (result.success) {
        // Auto-send cancellation email to customer
        if (result.customer_email && result.customer_name && result.consultant_name) {
          try {
            await apiService.sendCancellationEmail({
              appointment_id: appointmentId,
              customer_email: result.customer_email,
              customer_name: result.customer_name,
              consultant_name: result.consultant_name,
              date: result.date || '',
              time: result.time || '',
              duration: result.duration,
              description: result.description,
              cancellation_reason: result.cancellation_reason
            });
          } catch (emailErr) {
            // Email sending failed but appointment is already cancelled
            console.error('Failed to send cancellation email:', emailErr);
          }
        }
        loadAppointments();
      } else {
        setModalState({
          type: 'error',
          appointmentId: null,
          title: 'Lỗi',
          message: result.error || 'Không thể hủy cuộc hẹn'
        });
      }
    } catch (err) {
      console.error('Failed to deny:', err);
      setModalState({
        type: 'error',
        appointmentId: null,
        title: 'Lỗi',
        message: 'Không thể hủy cuộc hẹn'
      });
    } finally {
      setActionLoading(null);
    }
  };

  const handleComplete = (appointmentId: number) => {
    setModalState({
      type: 'complete',
      appointmentId,
      title: 'Hoàn Thành Cuộc Hẹn',
      message: 'Xác nhận cuộc hẹn này đã hoàn thành? Trạng thái sẽ được cập nhật và không thể thay đổi.'
    });
  };

  const completeAppointment = async () => {
    if (!modalState.appointmentId) return;
    setActionLoading(modalState.appointmentId);
    const appointmentId = modalState.appointmentId;
    setModalState({ type: null, appointmentId: null, title: '', message: '' });
    try {
      const result = await apiService.completeAppointment(consultantId, appointmentId);
      if (result.success) {
        loadAppointments();
      } else {
        setModalState({
          type: 'error',
          appointmentId: null,
          title: 'Lỗi',
          message: result.error || 'Không thể hoàn thành cuộc hẹn'
        });
      }
    } catch (err) {
      console.error('Failed to complete:', err);
      setModalState({
        type: 'error',
        appointmentId: null,
        title: 'Lỗi',
        message: 'Không thể hoàn thành cuộc hẹn'
      });
    } finally {
      setActionLoading(null);
    }
  };

  const getStatusBadge = (status: string) => {
    return (
      <span className={`px-3 py-1 rounded-full text-sm font-medium border ${getStatusBadgeClass(status)}`}>
        {statusToVietnamese(status)}
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
            Thử lại
          </button>
        </div>
      );
    }

    if (appointments.length === 0) {
      return (
        <div className="bg-white rounded-lg shadow p-12 text-center">
          <CalendarCheck className="w-16 h-16 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-gray-700">Không tìm thấy lịch hẹn</h3>
          <p className="text-gray-500 mt-2">
            {statusFilter === 'all' ? 'Bạn chưa có lịch hẹn nào' : `Không có lịch hẹn ${statusFilter === 'pending' ? 'chờ xác nhận' : statusFilter === 'confirmed' ? 'đã xác nhận' : statusFilter === 'completed' ? 'hoàn thành' : 'đã hủy'}`}
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
                <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">Ngày & Giờ</th>
                <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">Khách Hàng</th>
                <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">Thời Lượng</th>
                <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">Trạng Thái</th>
                <th className="text-left px-6 py-4 text-sm font-semibold text-gray-700">Hành Động</th>
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
                          {formatDateVN(apt.date, true)}
                        </p>
                        <p className="text-sm text-gray-500 flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {formatTimeVN(apt.time)}
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
                    <span className="text-gray-700">{apt.duration} phút</span>
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
                          Xác Nhận
                        </button>
                        <button
                          onClick={() => handleDeny(apt.appointmentid)}
                          disabled={actionLoading === apt.appointmentid}
                          className="flex items-center gap-1 px-3 py-1.5 bg-red-500 hover:bg-red-600 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                        >
                          <X className="w-4 h-4" />
                          Từ Chối
                        </button>
                      </div>
                    )}
                    {apt.status === 'confirmed' && (
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleComplete(apt.appointmentid)}
                          disabled={actionLoading === apt.appointmentid}
                          className="flex items-center gap-1 px-3 py-1.5 bg-blue-500 hover:bg-blue-600 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                        >
                          {actionLoading === apt.appointmentid ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <CheckCircle className="w-4 h-4" />
                          )}
                          Hoàn Thành
                        </button>
                        <button
                          onClick={() => handleDeny(apt.appointmentid)}
                          disabled={actionLoading === apt.appointmentid}
                          className="flex items-center gap-1 px-3 py-1.5 border border-red-300 text-red-600 hover:bg-red-50 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                        >
                          <X className="w-4 h-4" />
                          Hủy
                        </button>
                      </div>
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
          <h2 className="text-2xl font-bold text-gray-800">Cuộc Hẹn Của Tôi</h2>
          <p className="text-gray-500 mt-1">Quản lý các cuộc hẹn của bạn</p>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-gray-500" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
            >
              <option value="all">Tất Cả Trạng Thái</option>
              <option value="pending">Chờ Xác Nhận ({statusCounts.pending || 0})</option>
              <option value="confirmed">Đã Xác Nhận ({statusCounts.confirmed || 0})</option>
              <option value="completed">Hoàn Thành ({statusCounts.completed || 0})</option>
              <option value="cancelled">Đã Hủy ({statusCounts.cancelled || 0})</option>
            </select>
          </div>

          <button
            onClick={loadAppointments}
            className="flex items-center gap-2 px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Làm Mới
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Chờ Xác Nhận" count={statusCounts.pending || 0} color="yellow" />
        <StatCard label="Đã Xác Nhận" count={statusCounts.confirmed || 0} color="green" />
        <StatCard label="Hoàn Thành" count={statusCounts.completed || 0} color="blue" />
        <StatCard label="Đã Hủy" count={statusCounts.cancelled || 0} color="red" />
      </div>

      {/* Content */}
      {renderContent()}

      {/* Modal */}
      {modalState.type && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4" onClick={(e) => e.target === e.currentTarget && setModalState({ type: null, appointmentId: null, title: '', message: '' })}>
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full overflow-hidden">
            {/* Icon Header */}
            <div className={`flex items-center justify-center py-4 ${
              modalState.type === 'error' ? 'bg-red-50' :
              modalState.type === 'confirm' ? 'bg-green-50' :
              modalState.type === 'complete' ? 'bg-blue-50' :
              'bg-red-50'
            }`}>
              <div className={`w-16 h-16 rounded-full flex items-center justify-center ${
                modalState.type === 'error' ? 'bg-red-100' :
                modalState.type === 'confirm' ? 'bg-green-100' :
                modalState.type === 'complete' ? 'bg-blue-100' :
                'bg-red-100'
              }`}>
                {modalState.type === 'error' ? (
                  <AlertCircle className="w-8 h-8 text-red-600" />
                ) : modalState.type === 'confirm' ? (
                  <Check className="w-8 h-8 text-green-600" />
                ) : modalState.type === 'complete' ? (
                  <CheckCircle className="w-8 h-8 text-blue-600" />
                ) : (
                  <X className="w-8 h-8 text-red-600" />
                )}
              </div>
            </div>

            {/* Content */}
            <div className="px-6 py-4">
              <h3 className="text-lg font-semibold text-gray-900 text-center mb-2">
                {modalState.title}
              </h3>
              <p className="text-gray-600 text-sm text-center mb-4">
                {modalState.message}
              </p>

              {/* Cancel Reason Input */}
              {modalState.type === 'cancel' && (
                <div className="mb-4">
                  <label htmlFor="cancel-reason" className="block text-sm font-medium text-gray-700 mb-2">
                    Lý do hủy (không bắt buộc):
                  </label>
                  <textarea
                    id="cancel-reason"
                    value={modalState.cancelReason}
                    onChange={(e) => setModalState({ ...modalState, cancelReason: e.target.value })}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-teal-500 focus:border-teal-500 resize-none"
                    rows={3}
                    placeholder="Nhập lý do hủy cuộc hẹn..."
                  />
                </div>
              )}

              {/* Buttons */}
              <div className="flex items-center gap-3">
                {modalState.type !== 'error' && (
                  <button
                    onClick={() => setModalState({ type: null, appointmentId: null, title: '', message: '' })}
                    className="flex-1 px-4 py-2.5 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm font-medium transition-colors"
                  >
                    Hủy Bỏ
                  </button>
                )}
                <button
                  onClick={() => {
                    if (modalState.type === 'confirm') confirmAppointment();
                    else if (modalState.type === 'cancel') cancelAppointment();
                    else if (modalState.type === 'complete') completeAppointment();
                    else setModalState({ type: null, appointmentId: null, title: '', message: '' });
                  }}
                  className={`flex-1 px-4 py-2.5 rounded-lg text-sm font-medium text-white transition-colors ${
                    modalState.type === 'error' ? 'bg-gray-600 hover:bg-gray-700' :
                    modalState.type === 'confirm' ? 'bg-green-600 hover:bg-green-700' :
                    modalState.type === 'complete' ? 'bg-blue-600 hover:bg-blue-700' :
                    'bg-red-600 hover:bg-red-700'
                  }`}
                >
                  {modalState.type === 'error' ? 'Đóng' : 
                   modalState.type === 'confirm' ? 'Xác Nhận' : 
                   modalState.type === 'complete' ? 'Hoàn Thành' : 
                   'Hủy Cuộc Hẹn'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
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

