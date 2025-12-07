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
  getCustomers,
  getScheduleByConsultant
} from '../services/api.service';
import { formatDateVN, formatTimeVN, statusToVietnamese, getStatusBadgeClass } from '../utils/formatters';

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
  const [availableSlots, setAvailableSlots] = useState<any[]>([]);
  const [loadingSlots, setLoadingSlots] = useState(false);
  const [formData, setFormData] = useState({
    consultantid: 0,
    customerid: '',
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

  // Fetch available slots when consultant or date changes
  useEffect(() => {
    if (formData.consultantid && formData.date && isModalOpen) {
      fetchAvailableSlots(formData.consultantid, formData.date);
    }
  }, [formData.consultantid, formData.date, isModalOpen]);

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

  const fetchAvailableSlots = async (consultantId: number, date: string) => {
    if (!consultantId || !date) {
      setAvailableSlots([]);
      return;
    }

    console.log('Fetching slots for consultant:', consultantId, 'date:', date);
    setLoadingSlots(true);
    try {
      const response = await getScheduleByConsultant(
        consultantId,
        date,
        date
      );
      
      console.log('Schedule response:', response);
      
      // Filter only available slots for the selected date
      const slots = (response.schedules || [])
        .filter((slot: any) => slot.date === date && slot.isavailable && !slot.has_appointment)
        .map((slot: any) => ({
          scheduleid: slot.scheduleid,
          starttime: slot.starttime,
          endtime: slot.endtime
        }));
      
      setAvailableSlots(slots);
      
      // Auto-select first slot if available
      if (slots.length > 0 && !formData.time) {
        setFormData(prev => ({ ...prev, time: slots[0].starttime }));
      }
    } catch (error) {
      console.error('Error fetching available slots:', error);
      setAvailableSlots([]);
    } finally {
      setLoadingSlots(false);
    }
  };

  const handleCreate = () => {
    setEditingAppointment(null);
    setAvailableSlots([]);
    setFormData({
      consultantid: 0,
      customerid: '',
      date: getLocalDateString(),
      time: '',
      duration: 60,
      meetingurl: '',
      status: 'pending',
      description: ''
    });
    setAvailableSlots([]);
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
    setAvailableSlots([]);
    setIsModalOpen(true);
    // Fetch available slots for editing too
    fetchAvailableSlots(appointment.consultantid, appointment.date);
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

  // Load available slots when consultant and date are selected
  useEffect(() => {
    const loadAvailableSlots = async () => {
      if (!formData.consultantid || !formData.date) {
        setAvailableSlots([]);
        return;
      }

      try {
        setLoadingSlots(true);
        const response = await getScheduleByConsultant(
          formData.consultantid,
          formData.date,
          formData.date
        );

        if (response.success && response.schedules) {
          // Filter only available slots (no appointment and isavailable=true)
          const availableOnly = response.schedules.filter(
            (slot: any) => slot.isavailable && !slot.has_appointment
          );
          setAvailableSlots(availableOnly);
        } else {
          setAvailableSlots([]);
        }
      } catch (error) {
        console.error('Error loading available slots:', error);
        setAvailableSlots([]);
      } finally {
        setLoadingSlots(false);
      }
    };

    loadAvailableSlots();
  }, [formData.consultantid, formData.date]);

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
                          <div className="text-sm">{formatDateVN(appointment.date, true)}</div>
                          <div className="text-xs text-gray-400 dark:text-gray-500">{formatTimeVN(appointment.time)}</div>
                        </td>
                        <td className="px-4 py-3 text-gray-500 dark:text-gray-400 hidden lg:table-cell">
                          {appointment.duration} phút
                        </td>
                        <td className="px-4 py-3">
                          <span className={`badge ${getStatusBadgeClass(appointment.status)}`}>
                            {statusToVietnamese(appointment.status)}
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
                onChange={(e) => setFormData({ ...formData, customerid: e.target.value })}
                className="input"
              >
                <option value="">Chọn Khách Hàng</option>
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
              {loadingSlots ? (
                <div className="input flex items-center justify-center">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary-600 border-t-transparent"></div>
                  <span className="ml-2 text-sm">Đang tải slot...</span>
                </div>
              ) : availableSlots.length > 0 ? (
                <select
                  required
                  value={formData.time}
                  onChange={(e) => setFormData({ ...formData, time: e.target.value })}
                  className="input"
                >
                  <option value="">Chọn Giờ</option>
                  {availableSlots.map((slot) => {
                    const startTime = slot.starttime.substring(0, 5); // HH:MM
                    const endTime = slot.endtime.substring(0, 5); // HH:MM
                    return (
                      <option key={slot.scheduleid} value={slot.starttime}>
                        {startTime} - {endTime}
                      </option>
                    );
                  })}
                </select>
              ) : formData.consultantid && formData.date ? (
                <div className="input text-sm text-gray-500">
                  Không có slot khả dụng
                </div>
              ) : (
                <div className="input text-sm text-gray-500">
                  Chọn tư vấn viên và ngày trước
                </div>
              )}
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
