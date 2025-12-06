import { useState, useEffect, useMemo } from 'react';
import Header from '../components/Header';
import Button from '../components/Button';
import Modal from '../components/Modal';
import Pagination from '../components/Pagination';
import { Consultant, ConsultantSchedule } from '../types';
import { 
  getConsultantsWithAccountStatus, 
  createConsultant, 
  updateConsultant, 
  deleteConsultant, 
  getScheduleByConsultant,
  createConsultantSchedule,
  updateConsultantSchedule,
  deleteConsultantSchedule,
  createConsultantAccount,
  syncAllConsultantAccounts,
  resetConsultantPassword,
  deleteConsultantAccount
} from '../services/api.service';

// Helper function to get local date string (YYYY-MM-DD) instead of UTC
const getLocalDateString = (date: Date = new Date()): string => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

// Helper function to check if a slot is in the past (UTC+7 timezone)
const isPastSlot = (dateStr: string, timeStr: string): boolean => {
  // Parse slot datetime (YYYY-MM-DD and HH:MM:SS)
  const [year, month, day] = dateStr.split('-').map(Number);
  const [hours, minutes] = timeStr.split(':').map(Number);
  
  // Create date in local timezone (Vietnam UTC+7)
  const slotDate = new Date(year, month - 1, day, hours, minutes);
  const now = new Date();
  
  return slotDate < now;
};

export default function ConsultantsPage() {
  const [consultants, setConsultants] = useState<Consultant[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingConsultant, setEditingConsultant] = useState<Consultant | null>(null);
  const [formData, setFormData] = useState({
    fullname: '',
    email: '',
    phonenumber: '',
    specialties: '',
    qualifications: '',
    joindate: ''
  });

  // Schedule modal state
  const [isScheduleModalOpen, setIsScheduleModalOpen] = useState(false);
  const [selectedConsultant, setSelectedConsultant] = useState<Consultant | null>(null);
  const [schedules, setSchedules] = useState<ConsultantSchedule[]>([]);
  const [scheduleLoading, setScheduleLoading] = useState(false);

  // Schedule form state
  const [isScheduleFormOpen, setIsScheduleFormOpen] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState<ConsultantSchedule | null>(null);
  const [scheduleSubmitting, setScheduleSubmitting] = useState(false);
  const [scheduleFormData, setScheduleFormData] = useState({
    date: '',
    slots: [] as number[], // Array of selected slot ids (1-8)
    is_available: true // Only used for editing
  });

  // Fixed time slots
  const TIME_SLOTS = [
    { id: 1, label: 'Slot 1: 08:00 - 09:00', start: '08:00', end: '09:00' },
    { id: 2, label: 'Slot 2: 09:15 - 10:15', start: '09:15', end: '10:15' },
    { id: 3, label: 'Slot 3: 10:30 - 11:30', start: '10:30', end: '11:30' },
    { id: 4, label: 'Slot 4: 13:30 - 14:30', start: '13:30', end: '14:30' },
    { id: 5, label: 'Slot 5: 14:45 - 15:45', start: '14:45', end: '15:45' },
    { id: 6, label: 'Slot 6: 16:00 - 17:00', start: '16:00', end: '17:00' },
    { id: 7, label: 'Slot 7: 19:00 - 20:00', start: '19:00', end: '20:00' },
    { id: 8, label: 'Slot 8: 20:30 - 21:30', start: '20:30', end: '21:30' },
  ];

  // Account management state
  const [syncing, setSyncing] = useState(false);
  const [isAccountModalOpen, setIsAccountModalOpen] = useState(false);
  const [accountModalType, setAccountModalType] = useState<'create' | 'reset'>('create');
  const [selectedAccountConsultant, setSelectedAccountConsultant] = useState<Consultant | null>(null);
  const [accountActionLoading, setAccountActionLoading] = useState(false);

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const ITEMS_PER_PAGE = 10;

  // Paginated data
  const paginatedConsultants = useMemo(() => {
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    return consultants.slice(startIndex, startIndex + ITEMS_PER_PAGE);
  }, [consultants, currentPage]);

  const totalConsultantPages = Math.ceil(consultants.length / ITEMS_PER_PAGE);

  useEffect(() => {
    fetchConsultants();
  }, []);

  const fetchConsultants = async () => {
    try {
      setLoading(true);
      const response = await getConsultantsWithAccountStatus({ limit: 100, offset: 0 });
      setConsultants(response.consultants || []);
    } catch (error) {
      console.error('Error fetching consultants:', error);
    } finally {
      setLoading(false);
    }
  };

  // ==================== ACCOUNT MANAGEMENT HANDLERS ====================

  const handleSyncAllAccounts = async () => {
    if (!globalThis.confirm('Đồng bộ tất cả consultant accounts với Cognito?\nSẽ tạo account cho các consultant chưa có.')) {
      return;
    }
    
    setSyncing(true);
    try {
      const result = await syncAllConsultantAccounts();
      alert(`✅ Sync hoàn tất!\n• Tạo mới: ${result.created}\n• Đã tồn tại: ${result.already_exists}\n• Bỏ qua: ${result.skipped}\n• Lỗi: ${result.failed}`);
      fetchConsultants(); // Refresh list
    } catch (error) {
      console.error('Error syncing accounts:', error);
      alert('❌ Không thể đồng bộ accounts');
    } finally {
      setSyncing(false);
    }
  };

  const handleCreateAccount = (consultant: Consultant) => {
    setSelectedAccountConsultant(consultant);
    setAccountModalType('create');
    setIsAccountModalOpen(true);
  };

  const handleResetPassword = (consultant: Consultant) => {
    setSelectedAccountConsultant(consultant);
    setAccountModalType('reset');
    setIsAccountModalOpen(true);
  };

  const handleAccountAction = async () => {
    if (!selectedAccountConsultant) return;
    
    setAccountActionLoading(true);
    try {
      if (accountModalType === 'create') {
        const result = await createConsultantAccount({
          email: selectedAccountConsultant.email,
          consultant_id: selectedAccountConsultant.consultantid,
          fullname: selectedAccountConsultant.fullname,
          send_email: true
        });
        
        if (result.success) {
          alert(`✅ Tạo account thành công!\nEmail với mật khẩu tạm đã được gửi đến ${selectedAccountConsultant.email}`);
        } else {
          throw new Error(result.error || 'Failed to create account');
        }
      } else {
        const result = await resetConsultantPassword(selectedAccountConsultant.email);
        
        if (result.success) {
          alert(`✅ Reset password thành công!\nMật khẩu mới: ${result.temp_password}\n\nHãy gửi mật khẩu này cho consultant.`);
        } else {
          throw new Error(result.error || 'Failed to reset password');
        }
      }
      
      setIsAccountModalOpen(false);
      fetchConsultants(); // Refresh list
    } catch (error) {
      console.error('Account action error:', error);
      alert(`❌ Lỗi: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setAccountActionLoading(false);
    }
  };

  const handleDeleteAccount = async (consultant: Consultant) => {
    if (!globalThis.confirm(`Xóa Cognito account của ${consultant.fullname}?\nConsultant sẽ không thể đăng nhập Consultant Portal.`)) {
      return;
    }
    
    try {
      const result = await deleteConsultantAccount(consultant.email);
      if (result.success) {
        alert('✅ Đã xóa account');
        fetchConsultants();
      } else {
        throw new Error(result.error || 'Failed to delete account');
      }
    } catch (error) {
      console.error('Error deleting account:', error);
      alert(`❌ Lỗi: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  const getAccountStatusBadge = (consultant: Consultant) => {
    const status = (consultant as any).account_status;
    
    if (!status || !status.exists) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300">
          ❌ Chưa có
        </span>
      );
    }
    
    if (status.status === 'CONFIRMED') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
          ✅ Active
        </span>
      );
    }
    
    if (status.status === 'FORCE_CHANGE_PASSWORD') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400">
          ⚠️ Pending
        </span>
      );
    }
    
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300">
        {status.status}
      </span>
    );
  };

  const handleCreate = () => {
    setEditingConsultant(null);
    setFormData({
      fullname: '',
      email: '',
      phonenumber: '',
      specialties: '',
      qualifications: '',
      joindate: getLocalDateString()
    });
    setIsModalOpen(true);
  };

  const handleEdit = (consultant: Consultant) => {
    setEditingConsultant(consultant);
    setFormData({
      fullname: consultant.fullname,
      email: consultant.email,
      phonenumber: consultant.phonenumber || '',
      specialties: consultant.specialties || '',
      qualifications: consultant.qualifications || '',
      joindate: consultant.joindate || ''
    });
    setIsModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editingConsultant) {
        await updateConsultant(editingConsultant.consultantid, formData);
      } else {
        await createConsultant(formData);
      }
      setIsModalOpen(false);
      fetchConsultants();
    } catch (error) {
      console.error('Error saving consultant:', error);
      alert('Failed to save consultant');
    }
  };

  const handleDelete = async (consultantid: number) => {
    if (!globalThis.confirm('Are you sure you want to delete this consultant?')) {
      return;
    }
    try {
      await deleteConsultant(consultantid);
      fetchConsultants();
    } catch (error) {
      console.error('Error deleting consultant:', error);
      alert('Failed to delete consultant');
    }
  };

  const handleViewSchedule = async (consultant: Consultant) => {
    setSelectedConsultant(consultant);
    setIsScheduleModalOpen(true);
    setScheduleLoading(true);
    
    try {
      const response = await getScheduleByConsultant(consultant.consultantid);
      setSchedules(response.schedules || []);
    } catch (error) {
      console.error('Error fetching schedule:', error);
      setSchedules([]);
    } finally {
      setScheduleLoading(false);
    }
  };

  const handleAddSchedule = () => {
    setEditingSchedule(null);
    setScheduleFormData({
      date: getLocalDateString(),
      slots: [],
      is_available: true
    });
    setIsScheduleFormOpen(true);
  };

  const handleEditSchedule = (schedule: ConsultantSchedule) => {
    setEditingSchedule(schedule);
    // Find matching slot based on start time
    const matchingSlot = TIME_SLOTS.find(s => s.start === schedule.starttime.substring(0, 5));
    setScheduleFormData({
      date: schedule.date,
      slots: matchingSlot ? [matchingSlot.id] : [],
      is_available: schedule.isavailable
    });
    setIsScheduleFormOpen(true);
  };

  const handleDeleteSchedule = async (scheduleId: number) => {
    if (!globalThis.confirm('Bạn có chắc muốn xóa lịch này?')) {
      return;
    }
    try {
      await deleteConsultantSchedule(scheduleId);
      // Refresh schedules
      if (selectedConsultant) {
        const response = await getScheduleByConsultant(selectedConsultant.consultantid);
        setSchedules(response.schedules || []);
      }
    } catch (error) {
      console.error('Error deleting schedule:', error);
      alert('Không thể xóa lịch');
    }
  };

  const handleScheduleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedConsultant || scheduleSubmitting) return;
    
    if (scheduleFormData.slots.length === 0) {
      alert('Vui lòng chọn ít nhất một khung giờ');
      return;
    }

    setScheduleSubmitting(true);
    try {
      if (editingSchedule) {
        // Edit mode: only one slot
        const selectedSlot = TIME_SLOTS.find(s => s.id === scheduleFormData.slots[0]);
        if (selectedSlot) {
          await updateConsultantSchedule(editingSchedule.scheduleid, {
            date: scheduleFormData.date,
            start_time: selectedSlot.start,
            end_time: selectedSlot.end,
            is_available: scheduleFormData.is_available
          });
        }
        setIsScheduleFormOpen(false);
      } else {
        // Create mode: multiple slots, always is_available = true
        const createPromises = scheduleFormData.slots.map(slotId => {
          const slot = TIME_SLOTS.find(s => s.id === slotId);
          if (!slot) return Promise.resolve();
          return createConsultantSchedule({
            consultant_id: selectedConsultant.consultantid,
            date: scheduleFormData.date,
            start_time: slot.start,
            end_time: slot.end,
            is_available: true
          });
        });
        await Promise.all(createPromises);
        // Reset form but keep modal open for adding more
        setScheduleFormData({
          ...scheduleFormData,
          slots: []
        });
      }
      // Refresh schedules
      const response = await getScheduleByConsultant(selectedConsultant.consultantid);
      setSchedules(response.schedules || []);
    } catch (error) {
      console.error('Error saving schedule:', error);
      alert('Không thể lưu lịch. Lịch có thể đã tồn tại.');
    } finally {
      setScheduleSubmitting(false);
    }
  };

  const formatTime = (time: string) => {
    if (!time) return '-';
    return time.substring(0, 5); // "HH:MM:SS" -> "HH:MM"
  };

  return (
    <div className="min-h-screen">
      <Header 
        title="Quản lý Tư vấn viên" 
        subtitle="Quản lý hồ sơ và tài khoản cổng thông tin tư vấn viên"
        actions={
          <div className="flex items-center gap-2">
            <Button 
              onClick={handleSyncAllAccounts} 
              variant="secondary"
              disabled={syncing}
              icon={syncing ? "⏳" : "🔄"}
            >
              {syncing ? 'Đang đồng bộ...' : 'Đồng Bộ Tài Khoản'}
            </Button>
            <Button onClick={handleCreate} icon="➕">
              Thêm Tư Vấn Viên
            </Button>
          </div>
        }
      />

      <div className="p-4 sm:p-6 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Total: <span className="font-medium text-gray-900 dark:text-white">{consultants.length}</span> consultants
          </p>
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
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">Họ và tên</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300 hidden md:table-cell">Email</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300 hidden lg:table-cell">SĐT</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">Tài khoản</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300 hidden xl:table-cell">Chuyên môn</th>
                    <th className="px-4 py-3 text-right font-semibold text-gray-600 dark:text-gray-300">Hành động</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                  {paginatedConsultants.map((consultant) => (
                    <tr 
                      key={consultant.consultantid} 
                      className="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors cursor-pointer"
                      onClick={() => handleViewSchedule(consultant)}
                    >
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                        {consultant.consultantid}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <div className="h-8 w-8 rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center text-primary-600 dark:text-primary-400 font-medium text-sm">
                            {consultant.fullname.charAt(0)}
                          </div>
                          <div>
                            <span className="font-medium text-gray-900 dark:text-white">
                              {consultant.fullname}
                            </span>
                            <p className="text-xs text-gray-400 dark:text-gray-500">Click để xem lịch làm việc</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400 hidden md:table-cell">
                        {consultant.email}
                      </td>
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400 hidden lg:table-cell">
                        {consultant.phonenumber || '-'}
                      </td>
                      <td className="px-4 py-3">
                        {getAccountStatusBadge(consultant)}
                      </td>
                      <td className="px-4 py-3 hidden xl:table-cell">
                        <div className="max-w-[200px] truncate text-gray-500 dark:text-gray-400">
                          {consultant.specialties || '-'}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-1">
                          {/* Account actions */}
                          {!(consultant as any).account_status?.exists ? (
                            <button
                              onClick={(e) => { e.stopPropagation(); handleCreateAccount(consultant); }}
                              className="p-2 rounded-lg text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-900/20 transition-colors"
                              title="Tạo account"
                            >
                              🔑
                            </button>
                          ) : (
                            <>
                            <button
                              onClick={(e) => { e.stopPropagation(); handleResetPassword(consultant); }}
                              className="p-2 rounded-lg text-orange-600 dark:text-orange-400 hover:bg-orange-50 dark:hover:bg-orange-900/20 transition-colors"
                              title="Đặt lại mật khẩu"
                            >
                                🔄
                              </button>
                              <button
                                onClick={(e) => { e.stopPropagation(); handleDeleteAccount(consultant); }}
                                className="p-2 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                                title="Xóa account"
                              >
                                🚫
                              </button>
                            </>
                          )}
                          {/* Edit/Delete consultant */}
                          <button
                            onClick={(e) => { e.stopPropagation(); handleEdit(consultant); }}
                            className="p-2 rounded-lg text-primary-600 dark:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors"
                            title="Chỉnh sửa"
                          >
                            ✏️
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleDelete(consultant.consultantid); }}
                            className="p-2 rounded-lg text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                            title="Xóa"
                          >
                            🗑️
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              currentPage={currentPage}
              totalPages={totalConsultantPages}
              onPageChange={setCurrentPage}
              totalItems={consultants.length}
              itemsPerPage={ITEMS_PER_PAGE}
            />
          </div>
        )}
      </div>

      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingConsultant ? 'Chỉnh Sửa Tư Vấn Viên' : 'Thêm Tư Vấn Viên Mới'}
        size="lg"
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              Họ Tên *
            </label>
            <input
              type="text"
              required
              value={formData.fullname}
              onChange={(e) => setFormData({ ...formData, fullname: e.target.value })}
              className="input"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              Email *
            </label>
            <input
              type="email"
              required
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              className="input"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Số Điện Thoại
              </label>
              <input
                type="tel"
                value={formData.phonenumber}
                onChange={(e) => setFormData({ ...formData, phonenumber: e.target.value })}
                className="input"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Ngày Tham Gia
              </label>
              <input
                type="date"
                value={formData.joindate}
                onChange={(e) => setFormData({ ...formData, joindate: e.target.value })}
                className="input"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              Chuyên Môn
            </label>
            <textarea
              value={formData.specialties}
              onChange={(e) => setFormData({ ...formData, specialties: e.target.value })}
              rows={2}
              className="input resize-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              Bằng Cấp
            </label>
            <textarea
              value={formData.qualifications}
              onChange={(e) => setFormData({ ...formData, qualifications: e.target.value })}
              rows={2}
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
              {editingConsultant ? 'Cập Nhật' : 'Tạo Mới'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Schedule Modal */}
      <Modal
        isOpen={isScheduleModalOpen}
        onClose={() => setIsScheduleModalOpen(false)}
        title={`Lịch làm việc - ${selectedConsultant?.fullname || ''}`}
        size="lg"
      >
        <div className="space-y-4">
          {/* Consultant Info */}
          {selectedConsultant && (
            <div className="flex items-center justify-between gap-4 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
              <div className="flex items-center gap-4">
                <div className="h-16 w-16 rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center text-primary-600 dark:text-primary-400 font-bold text-xl">
                  {selectedConsultant.fullname.charAt(0)}
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900 dark:text-white">{selectedConsultant.fullname}</h3>
                  <p className="text-sm text-gray-500 dark:text-gray-400">{selectedConsultant.email}</p>
                  {selectedConsultant.specialties && (
                    <p className="text-sm text-primary-600 dark:text-primary-400 mt-1">{selectedConsultant.specialties}</p>
                  )}
                </div>
              </div>
              <Button onClick={handleAddSchedule} icon="➕" size="sm">
                Thêm lịch
              </Button>
            </div>
          )}

          {/* Schedule List */}
          {scheduleLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-600 border-t-transparent"></div>
            </div>
          ) : schedules.length === 0 ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              <p className="text-4xl mb-2">📅</p>
              <p>Chưa có lịch làm việc nào được thiết lập</p>
              <p className="text-sm mt-2">Nhấn "Thêm lịch" để tạo lịch mới</p>
            </div>
          ) : (
            <>
              {/* Group schedules by date */}
              {Object.entries(
                schedules.reduce((acc, schedule) => {
                  if (!acc[schedule.date]) acc[schedule.date] = [];
                  acc[schedule.date].push(schedule);
                  return acc;
                }, {} as Record<string, typeof schedules>)
              )
              .sort(([dateA], [dateB]) => dateA.localeCompare(dateB))
              .map(([date, daySchedules]) => {
                const dateObj = new Date(date + 'T00:00:00');
                const dayName = dateObj.toLocaleDateString('vi-VN', { weekday: 'long' });
                const formattedDate = dateObj.toLocaleDateString('vi-VN', { year: 'numeric', month: 'long', day: 'numeric' });
                
                return (
                  <div key={date} className="mb-6 last:mb-0">
                    <div className="flex items-center justify-between mb-3 pb-2 border-b border-gray-200 dark:border-gray-700">
                      <h4 className="font-semibold text-gray-900 dark:text-white">
                        {dayName}, {formattedDate}
                      </h4>
                      <span className="text-sm text-gray-500 dark:text-gray-400">
                        {daySchedules.length} khung giờ
                      </span>
                    </div>
                    
                    <div className="space-y-2">
                      {daySchedules.map((schedule) => {
                        // Check if slot is in the past
                        const isPast = isPastSlot(schedule.date, schedule.endtime);
                        
                        // Determine status label and styling
                        let statusLabel = '';
                        let statusClass = '';
                        
                        if (schedule.has_appointment || !schedule.isavailable) {
                          statusLabel = '✗ Không khả dụng';
                          statusClass = 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400';
                        } else if (isPast) {
                          statusLabel = 'Đã qua';
                          statusClass = 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400';
                        } else {
                          statusLabel = '✓ Có thể đặt';
                          statusClass = 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400';
                        }
                        
                        return (
                          <div key={schedule.scheduleid} className="flex items-center justify-between p-3 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 hover:shadow-sm transition-shadow">
                            <div className="flex items-center gap-4">
                              <div className="text-gray-900 dark:text-white font-medium">
                                {formatTime(schedule.starttime)} - {formatTime(schedule.endtime)}
                              </div>
                              <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${statusClass}`}>
                                {statusLabel}
                              </span>
                            </div>
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => handleEditSchedule(schedule)}
                                className="p-2 rounded-lg text-primary-600 dark:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors"
                                title="Edit"
                              >
                                ✏️
                              </button>
                              <button
                                onClick={() => handleDeleteSchedule(schedule.scheduleid)}
                                className="p-2 rounded-lg text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                                title="Delete"
                              >
                                🗑️
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </>
          )}
        </div>
      </Modal>

      {/* Schedule Form Modal */}
      <Modal
        isOpen={isScheduleFormOpen}
        onClose={() => setIsScheduleFormOpen(false)}
        title={editingSchedule ? 'Chỉnh sửa lịch' : 'Thêm lịch mới'}
        size="md"
      >
        <form onSubmit={handleScheduleSubmit} className="space-y-4">
          <div>
            <label htmlFor="schedule-date" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              Ngày *
            </label>
            <input
              id="schedule-date"
              type="date"
              required
              value={scheduleFormData.date}
              onChange={(e) => setScheduleFormData({ ...scheduleFormData, date: e.target.value })}
              className="input"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              Khung giờ * {!editingSchedule && <span className="text-xs text-gray-500">(có thể chọn nhiều)</span>}
            </label>
            <div className="grid grid-cols-2 gap-2">
              {TIME_SLOTS.map((slot) => {
                const isSelected = scheduleFormData.slots.includes(slot.id);
                return (
                  <button
                    key={slot.id}
                    type="button"
                    onClick={() => {
                      if (editingSchedule) {
                        // Edit mode: single selection
                        setScheduleFormData({ ...scheduleFormData, slots: [slot.id] });
                      } else {
                        // Create mode: toggle multi-selection
                        const newSlots = isSelected
                          ? scheduleFormData.slots.filter(id => id !== slot.id)
                          : [...scheduleFormData.slots, slot.id];
                        setScheduleFormData({ ...scheduleFormData, slots: newSlots });
                      }
                    }}
                    className={`p-3 text-sm rounded-lg border-2 transition-all text-left ${
                      isSelected
                        ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
                        : 'border-gray-200 dark:border-gray-600 hover:border-gray-300 dark:hover:border-gray-500 text-gray-700 dark:text-gray-300'
                    }`}
                  >
                    <div className="font-medium">{slot.start} - {slot.end}</div>
                  </button>
                );
              })}
            </div>
          </div>

          {editingSchedule && (
            <div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={scheduleFormData.is_available}
                  onChange={(e) => setScheduleFormData({ ...scheduleFormData, is_available: e.target.checked })}
                  className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                />
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  Có thể đặt lịch
                </span>
              </label>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setIsScheduleFormOpen(false)}
              disabled={scheduleSubmitting}
            >
              {editingSchedule ? 'Hủy' : 'Đóng'}
            </Button>
            <Button type="submit" disabled={scheduleSubmitting}>
              {scheduleSubmitting 
                ? 'Đang lưu...' 
                : editingSchedule 
                  ? 'Cập nhật' 
                  : `Thêm ${scheduleFormData.slots.length > 0 ? `(${scheduleFormData.slots.length})` : ''}`
              }
            </Button>
          </div>
        </form>
      </Modal>

      {/* Account Management Modal */}
      <Modal
        isOpen={isAccountModalOpen}
        onClose={() => setIsAccountModalOpen(false)}
        title={accountModalType === 'create' ? '🔑 Tạo Account Portal' : '🔄 Reset Password'}
        size="sm"
      >
        <div className="space-y-4">
          {selectedAccountConsultant && (
            <>
              <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                <div className="flex items-center gap-3">
                  <div className="h-12 w-12 rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center text-primary-600 dark:text-primary-400 font-medium text-lg">
                    {selectedAccountConsultant.fullname.charAt(0)}
                  </div>
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">
                      {selectedAccountConsultant.fullname}
                    </p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      {selectedAccountConsultant.email}
                    </p>
                  </div>
                </div>
              </div>

              {accountModalType === 'create' ? (
                <div className="text-sm text-gray-600 dark:text-gray-300">
                  <p className="mb-2">📧 Một email với mật khẩu tạm thời sẽ được gửi đến consultant.</p>
                  <p>Consultant cần đổi mật khẩu khi đăng nhập lần đầu.</p>
                </div>
              ) : (
                <div className="text-sm text-gray-600 dark:text-gray-300">
                  <p className="mb-2">🔐 Mật khẩu mới sẽ được tạo và hiển thị sau khi hoàn tất.</p>
                  <p>Consultant cần đổi mật khẩu khi đăng nhập tiếp theo.</p>
                </div>
              )}

              <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => setIsAccountModalOpen(false)}
                >
                  Hủy
                </Button>
                <Button 
                  onClick={handleAccountAction} 
                  disabled={accountActionLoading}
                >
                  {accountActionLoading 
                    ? '⏳ Đang xử lý...' 
                    : accountModalType === 'create' 
                      ? '✅ Tạo Account' 
                      : '🔄 Reset Password'
                  }
                </Button>
              </div>
            </>
          )}
        </div>
      </Modal>
    </div>
  );
}
