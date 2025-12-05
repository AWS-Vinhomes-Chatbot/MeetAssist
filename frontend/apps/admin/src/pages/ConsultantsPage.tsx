import { useState, useEffect } from 'react';
import Header from '../components/Header';
import Button from '../components/Button';
import Modal from '../components/Modal';
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
  generateConsultantSchedule,
  createConsultantAccount,
  syncAllConsultantAccounts,
  resetConsultantPassword,
  deleteConsultantAccount
} from '../services/api.service';

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
  const [scheduleFormData, setScheduleFormData] = useState({
    date: '',
    start_time: '',
    end_time: '',
    is_available: true
  });

  // Generate schedule state
  const [isGenerateFormOpen, setIsGenerateFormOpen] = useState(false);
  const [generateFormData, setGenerateFormData] = useState({
    date_from: '',
    date_to: '',
    work_start: '09:00',
    work_end: '18:00',
    slot_duration: 60,
    exclude_weekends: true
  });
  const [generating, setGenerating] = useState(false);

  // Account management state
  const [syncing, setSyncing] = useState(false);
  const [isAccountModalOpen, setIsAccountModalOpen] = useState(false);
  const [accountModalType, setAccountModalType] = useState<'create' | 'reset'>('create');
  const [selectedAccountConsultant, setSelectedAccountConsultant] = useState<Consultant | null>(null);
  const [accountActionLoading, setAccountActionLoading] = useState(false);

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
      joindate: new Date().toISOString().split('T')[0]
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
      date: new Date().toISOString().split('T')[0],
      start_time: '09:00',
      end_time: '17:00',
      is_available: true
    });
    setIsScheduleFormOpen(true);
  };

  const handleEditSchedule = (schedule: ConsultantSchedule) => {
    setEditingSchedule(schedule);
    setScheduleFormData({
      date: schedule.date,
      start_time: schedule.starttime.substring(0, 5),
      end_time: schedule.endtime.substring(0, 5),
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
    if (!selectedConsultant) return;

    try {
      if (editingSchedule) {
        await updateConsultantSchedule(editingSchedule.scheduleid, scheduleFormData);
      } else {
        await createConsultantSchedule({
          consultant_id: selectedConsultant.consultantid,
          ...scheduleFormData
        });
      }
      setIsScheduleFormOpen(false);
      // Refresh schedules
      const response = await getScheduleByConsultant(selectedConsultant.consultantid);
      setSchedules(response.schedules || []);
    } catch (error) {
      console.error('Error saving schedule:', error);
      alert('Không thể lưu lịch');
    }
  };

  const handleOpenGenerateForm = () => {
    // Default: next 7 days
    const today = new Date();
    const nextWeek = new Date(today);
    nextWeek.setDate(nextWeek.getDate() + 7);
    
    setGenerateFormData({
      date_from: today.toISOString().split('T')[0],
      date_to: nextWeek.toISOString().split('T')[0],
      work_start: '09:00',
      work_end: '18:00',
      slot_duration: 60,
      exclude_weekends: true
    });
    setIsGenerateFormOpen(true);
  };

  const handleGenerateSchedule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedConsultant) return;

    setGenerating(true);
    try {
      const result = await generateConsultantSchedule({
        consultant_id: selectedConsultant.consultantid,
        ...generateFormData
      });
      
      setIsGenerateFormOpen(false);
      alert(`✅ ${result.message}`);
      
      // Refresh schedules
      const response = await getScheduleByConsultant(selectedConsultant.consultantid);
      setSchedules(response.schedules || []);
    } catch (error) {
      console.error('Error generating schedule:', error);
      alert('Không thể tạo lịch tự động');
    } finally {
      setGenerating(false);
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
        subtitle="Manage consultant profiles and portal accounts"
        actions={
          <div className="flex items-center gap-2">
            <Button 
              onClick={handleSyncAllAccounts} 
              variant="secondary"
              disabled={syncing}
              icon={syncing ? "⏳" : "🔄"}
            >
              {syncing ? 'Syncing...' : 'Sync Accounts'}
            </Button>
            <Button onClick={handleCreate} icon="➕">
              Add Consultant
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
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">Full Name</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300 hidden md:table-cell">Email</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300 hidden lg:table-cell">Phone</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">Account</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300 hidden xl:table-cell">Specialties</th>
                    <th className="px-4 py-3 text-right font-semibold text-gray-600 dark:text-gray-300">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                  {consultants.map((consultant) => (
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
                                title="Reset password"
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
                            title="Edit"
                          >
                            ✏️
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleDelete(consultant.consultantid); }}
                            className="p-2 rounded-lg text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                            title="Delete"
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
          </div>
        )}
      </div>

      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingConsultant ? 'Edit Consultant' : 'Add New Consultant'}
        size="lg"
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              Full Name *
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
                Phone Number
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
                Join Date
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
              Specialties
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
              Qualifications
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
              Cancel
            </Button>
            <Button type="submit">
              {editingConsultant ? 'Update' : 'Create'}
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
              <Button onClick={handleOpenGenerateForm} variant="secondary" icon="🔄" size="sm">
                Tạo tự động
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
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 dark:bg-gray-800/50">
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">Ngày</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">Giờ bắt đầu</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">Giờ kết thúc</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">Trạng thái</th>
                    <th className="px-4 py-3 text-right font-semibold text-gray-600 dark:text-gray-300">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                  {schedules.map((schedule) => (
                    <tr key={schedule.scheduleid} className="hover:bg-gray-50 dark:hover:bg-gray-700/30">
                      <td className="px-4 py-3 text-gray-900 dark:text-white">
                        {schedule.date}
                      </td>
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                        {formatTime(schedule.starttime)}
                      </td>
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                        {formatTime(schedule.endtime)}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                          schedule.isavailable 
                            ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                            : 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
                        }`}>
                          {schedule.isavailable 
                            ? '✓ Có thể đặt' 
                            : '✗ Không khả dụng'}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-2">
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
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="schedule-start" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Giờ bắt đầu *
              </label>
              <input
                id="schedule-start"
                type="time"
                required
                value={scheduleFormData.start_time}
                onChange={(e) => setScheduleFormData({ ...scheduleFormData, start_time: e.target.value })}
                className="input"
              />
            </div>
            <div>
              <label htmlFor="schedule-end" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Giờ kết thúc *
              </label>
              <input
                id="schedule-end"
                type="time"
                required
                value={scheduleFormData.end_time}
                onChange={(e) => setScheduleFormData({ ...scheduleFormData, end_time: e.target.value })}
                className="input"
              />
            </div>
          </div>

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

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setIsScheduleFormOpen(false)}
            >
              Hủy
            </Button>
            <Button type="submit">
              {editingSchedule ? 'Cập nhật' : 'Tạo mới'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Generate Schedule Modal */}
      <Modal
        isOpen={isGenerateFormOpen}
        onClose={() => setIsGenerateFormOpen(false)}
        title="Tạo lịch tự động"
        size="md"
      >
        <form onSubmit={handleGenerateSchedule} className="space-y-4">
          <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-sm text-blue-700 dark:text-blue-300">
            💡 Hệ thống sẽ tự động tạo các slot theo khung giờ được chọn
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="gen-date-from" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Từ ngày *
              </label>
              <input
                id="gen-date-from"
                type="date"
                required
                value={generateFormData.date_from}
                onChange={(e) => setGenerateFormData({ ...generateFormData, date_from: e.target.value })}
                className="input"
              />
            </div>
            <div>
              <label htmlFor="gen-date-to" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Đến ngày *
              </label>
              <input
                id="gen-date-to"
                type="date"
                required
                value={generateFormData.date_to}
                onChange={(e) => setGenerateFormData({ ...generateFormData, date_to: e.target.value })}
                className="input"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="gen-work-start" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Giờ bắt đầu làm việc
              </label>
              <input
                id="gen-work-start"
                type="time"
                value={generateFormData.work_start}
                onChange={(e) => setGenerateFormData({ ...generateFormData, work_start: e.target.value })}
                className="input"
              />
            </div>
            <div>
              <label htmlFor="gen-work-end" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Giờ kết thúc làm việc
              </label>
              <input
                id="gen-work-end"
                type="time"
                value={generateFormData.work_end}
                onChange={(e) => setGenerateFormData({ ...generateFormData, work_end: e.target.value })}
                className="input"
              />
            </div>
          </div>

          <div>
            <label htmlFor="gen-slot-duration" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              Thời lượng mỗi slot (phút)
            </label>
            <select
              id="gen-slot-duration"
              value={generateFormData.slot_duration}
              onChange={(e) => setGenerateFormData({ ...generateFormData, slot_duration: parseInt(e.target.value) })}
              className="input"
            >
              <option value={30}>30 phút</option>
              <option value={45}>45 phút</option>
              <option value={60}>1 tiếng</option>
              <option value={90}>1 tiếng 30 phút</option>
              <option value={120}>2 tiếng</option>
            </select>
          </div>

          <div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={generateFormData.exclude_weekends}
                onChange={(e) => setGenerateFormData({ ...generateFormData, exclude_weekends: e.target.checked })}
                className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
              />
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Bỏ qua cuối tuần (Thứ 7, Chủ nhật)
              </span>
            </label>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setIsGenerateFormOpen(false)}
            >
              Hủy
            </Button>
            <Button type="submit" disabled={generating}>
              {generating ? '⏳ Đang tạo...' : '🔄 Tạo lịch'}
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
