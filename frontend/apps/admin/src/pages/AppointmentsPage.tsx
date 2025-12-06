import { useState, useEffect, useMemo } from 'react';
import Header from '../components/Header';
import Button from '../components/Button';
import Modal from '../components/Modal';
import Pagination from '../components/Pagination';
import { Appointment, Consultant, Customer } from '../types';
import { 
  getAppointments, 
  createAppointment, 
  updateAppointment, 
  deleteAppointment,
  getConsultants,
  getCustomers
} from '../services/api.service';

// Helper function to get local date string (YYYY-MM-DD) instead of UTC
const getLocalDateString = (date: Date = new Date()): string => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

export default function AppointmentsPage() {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [consultants, setConsultants] = useState<Consultant[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingAppointment, setEditingAppointment] = useState<Appointment | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [formData, setFormData] = useState({
    consultantid: 0,
    customerid: 0,
    date: '',
    time: '',
    duration: 60,
    meetingurl: '',
    status: 'pending',
    description: ''
  });

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const ITEMS_PER_PAGE = 10;

  // Paginated data
  const paginatedAppointments = useMemo(() => {
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    return appointments.slice(startIndex, startIndex + ITEMS_PER_PAGE);
  }, [appointments, currentPage]);

  const totalPages = Math.ceil(appointments.length / ITEMS_PER_PAGE);

  useEffect(() => {
    fetchAppointments();
    fetchConsultants();
    fetchCustomers();
  }, [statusFilter]);

  // Reset to page 1 when filter changes
  useEffect(() => {
    setCurrentPage(1);
  }, [statusFilter]);

  const fetchAppointments = async () => {
    try {
      setLoading(true);
      const params: Record<string, unknown> = { limit: 100, offset: 0 };
      if (statusFilter) params.status = statusFilter;
      
      const response = await getAppointments(params);
      setAppointments(response.appointments || []);
    } catch (error) {
      console.error('Error fetching appointments:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchConsultants = async () => {
    try {
      const response = await getConsultants({ limit: 100, offset: 0 });
      setConsultants(response.consultants || []);
    } catch (error) {
      console.error('Error fetching consultants:', error);
    }
  };

  const fetchCustomers = async () => {
    try {
      const response = await getCustomers({ limit: 100, offset: 0 });
      setCustomers(response.customers || []);
    } catch (error) {
      console.error('Error fetching customers:', error);
    }
  };

  const handleCreate = () => {
    setEditingAppointment(null);
    setFormData({
      consultantid: 0,
      customerid: 0,
      date: getLocalDateString(),
      time: '09:00',
      duration: 60,
      meetingurl: '',
      status: 'pending',
      description: ''
    });
    setIsModalOpen(true);
  };

  const handleEdit = (appointment: Appointment) => {
    setEditingAppointment(appointment);
    setFormData({
      consultantid: appointment.consultantid,
      customerid: appointment.customerid,
      date: appointment.date,
      time: appointment.time,
      duration: appointment.duration,
      meetingurl: appointment.meetingurl || '',
      status: appointment.status,
      description: appointment.description || ''
    });
    setIsModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editingAppointment) {
        await updateAppointment(editingAppointment.appointmentid, formData);
      } else {
        await createAppointment(formData);
      }
      setIsModalOpen(false);
      fetchAppointments();
    } catch (error) {
      console.error('Error saving appointment:', error);
      alert('Failed to save appointment');
    }
  };

  const handleDelete = async (appointmentid: number) => {
    if (!globalThis.confirm('Are you sure you want to delete this appointment?')) {
      return;
    }
    try {
      await deleteAppointment(appointmentid);
      fetchAppointments();
    } catch (error) {
      console.error('Error deleting appointment:', error);
      alert('Failed to delete appointment');
    }
  };

  const getStatusBadge = (status: string) => {
    const statusColors: Record<string, string> = {
      pending: 'badge-warning',
      confirmed: 'badge-info',
      completed: 'badge-success',
      cancelled: 'badge-error'
    };
    return statusColors[status] || 'badge-neutral';
  };

  return (
    <div className="min-h-screen">
      <Header 
        title="Quản lý Lịch hẹn" 
        subtitle="Quản lý các cuộc hẹn tư vấn"
        actions={
          <Button onClick={handleCreate} icon="➕">
            Thêm Lịch Hẹn
          </Button>
        }
      />

      <div className="p-4 sm:p-6 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Tổng số: <span className="font-medium text-gray-900 dark:text-white">{appointments.length}</span> lịch hẹn
          </p>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="input w-full sm:w-auto sm:min-w-[150px]"
          >
            <option value="">Tất Cả Trạng Thái</option>
            <option value="pending">Chờ Xác Nhận</option>
            <option value="confirmed">Đã Xác Nhận</option>
            <option value="completed">Hoàn Thành</option>
            <option value="cancelled">Đã Hủy</option>
          </select>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-600 border-t-transparent"></div>
          </div>
        ) : (
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 dark:bg-gray-800/50">
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">ID</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">Khách Hàng</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300 hidden md:table-cell">Tư Vấn Viên</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">Ngày & Giờ</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300 hidden lg:table-cell">Thời Lượng</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">Trạng Thái</th>
                    <th className="px-4 py-3 text-right font-semibold text-gray-600 dark:text-gray-300">Hành Động</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                  {paginatedAppointments.map((appointment) => {
                    const consultant = consultants.find(c => c.consultantid === appointment.consultantid);
                    const customer = customers.find(c => c.customerid === appointment.customerid);
                    
                    return (
                      <tr key={appointment.appointmentid} className="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                        <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                          {appointment.appointmentid}
                        </td>
                        <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">
                          {customer?.fullname || `Khách Hàng #${appointment.customerid}`}
                        </td>
                        <td className="px-4 py-3 text-gray-500 dark:text-gray-400 hidden md:table-cell">
                          {consultant?.fullname || `Tư Vấn Viên #${appointment.consultantid}`}
                        </td>
                        <td className="px-4 py-3 text-gray-600 dark:text-gray-400">
                          <div className="text-sm">{appointment.date}</div>
                          <div className="text-xs text-gray-400 dark:text-gray-500">{appointment.time}</div>
                        </td>
                        <td className="px-4 py-3 text-gray-500 dark:text-gray-400 hidden lg:table-cell">
                          {appointment.duration} phút
                        </td>
                        <td className="px-4 py-3">
                          <span className={`badge ${getStatusBadge(appointment.status)}`}>
                            {appointment.status}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => handleEdit(appointment)}
                              className="p-2 rounded-lg text-primary-600 dark:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors"
                              title="Chỉnh sửa"
                            >
                              ✏️
                            </button>
                            <button
                              onClick={() => handleDelete(appointment.appointmentid)}
                              className="p-2 rounded-lg text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                              title="Xóa"
                            >
                              🗑️
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              onPageChange={setCurrentPage}
              totalItems={appointments.length}
              itemsPerPage={ITEMS_PER_PAGE}
            />
          </div>
        )}
      </div>

      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingAppointment ? 'Chỉnh Sửa Lịch Hẹn' : 'Thêm Lịch Hẹn Mới'}
        size="lg"
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Khách Hàng *
              </label>
              <select
                required
                value={formData.customerid}
                onChange={(e) => setFormData({ ...formData, customerid: parseInt(e.target.value) })}
                className="input"
              >
                <option value={0}>Chọn Khách Hàng</option>
                {customers.map(customer => (
                  <option key={customer.customerid} value={customer.customerid}>
                    {customer.fullname}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Tư Vấn Viên *
              </label>
              <select
                required
                value={formData.consultantid}
                onChange={(e) => setFormData({ ...formData, consultantid: parseInt(e.target.value) })}
                className="input"
              >
                <option value={0}>Chọn Tư Vấn Viên</option>
                {consultants.map(consultant => (
                  <option key={consultant.consultantid} value={consultant.consultantid}>
                    {consultant.fullname}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Ngày *
              </label>
              <input
                type="date"
                required
                value={formData.date}
                onChange={(e) => setFormData({ ...formData, date: e.target.value })}
                className="input"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Giờ *
              </label>
              <input
                type="time"
                required
                value={formData.time}
                onChange={(e) => setFormData({ ...formData, time: e.target.value })}
                className="input"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Thời Lượng (phút)
              </label>
              <input
                type="number"
                value={formData.duration}
                onChange={(e) => setFormData({ ...formData, duration: parseInt(e.target.value) })}
                className="input"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Trạng Thái *
              </label>
              <select
                required
                value={formData.status}
                onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                className="input"
              >
                <option value="pending">Chờ Xác Nhận</option>
                <option value="confirmed">Đã Xác Nhận</option>
                <option value="completed">Hoàn Thành</option>
                <option value="cancelled">Đã Hủy</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              Mô Tả
            </label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              rows={3}
              className="input resize-none"
            />
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setIsModalOpen(false)}
            >
              Hủy
            </Button>
            <Button type="submit">
              {editingAppointment ? 'Cập Nhật' : 'Tạo Mới'}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
