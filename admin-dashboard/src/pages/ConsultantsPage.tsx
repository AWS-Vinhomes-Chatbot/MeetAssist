import { useState, useEffect } from 'react';
import Header from '../components/Header';
import Button from '../components/Button';
import Modal from '../components/Modal';
import { Consultant } from '../types';
import { getConsultants, createConsultant, updateConsultant, deleteConsultant } from '../services/api.service';

export default function ConsultantsPage() {
  const [consultants, setConsultants] = useState<Consultant[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingConsultant, setEditingConsultant] = useState<Consultant | null>(null);
  const [formData, setFormData] = useState({
    fullname: '',
    email: '',
    phonenumber: '',
    imageurl: '',
    specialties: '',
    qualifications: '',
    joindate: ''
  });

  useEffect(() => {
    fetchConsultants();
  }, []);

  const fetchConsultants = async () => {
    try {
      setLoading(true);
      const response = await getConsultants({ limit: 100, offset: 0 });
      setConsultants(response.consultants || []);
    } catch (error) {
      console.error('Error fetching consultants:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = () => {
    setEditingConsultant(null);
    setFormData({
      fullname: '',
      email: '',
      phonenumber: '',
      imageurl: '',
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
      imageurl: consultant.imageurl || '',
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

  return (
    <div className="min-h-screen">
      <Header 
        title="Quản lý Tư vấn viên" 
        subtitle="Manage consultant profiles and information"
        actions={
          <Button onClick={handleCreate} icon="➕">
            Add Consultant
          </Button>
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
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300 hidden xl:table-cell">Specialties</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300 hidden lg:table-cell">Join Date</th>
                    <th className="px-4 py-3 text-right font-semibold text-gray-600 dark:text-gray-300">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                  {consultants.map((consultant) => (
                    <tr key={consultant.consultantid} className="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                        {consultant.consultantid}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          {consultant.imageurl ? (
                            <img 
                              src={consultant.imageurl} 
                              alt={consultant.fullname}
                              className="h-8 w-8 rounded-full object-cover"
                            />
                          ) : (
                            <div className="h-8 w-8 rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center text-primary-600 dark:text-primary-400 font-medium text-sm">
                              {consultant.fullname.charAt(0)}
                            </div>
                          )}
                          <span className="font-medium text-gray-900 dark:text-white">
                            {consultant.fullname}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400 hidden md:table-cell">
                        {consultant.email}
                      </td>
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400 hidden lg:table-cell">
                        {consultant.phonenumber || '-'}
                      </td>
                      <td className="px-4 py-3 hidden xl:table-cell">
                        <div className="max-w-[200px] truncate text-gray-500 dark:text-gray-400">
                          {consultant.specialties || '-'}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400 hidden lg:table-cell">
                        {consultant.joindate || '-'}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => handleEdit(consultant)}
                            className="p-2 rounded-lg text-primary-600 dark:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors"
                            title="Edit"
                          >
                            ✏️
                          </button>
                          <button
                            onClick={() => handleDelete(consultant.consultantid)}
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
              Image URL
            </label>
            <input
              type="url"
              value={formData.imageurl}
              onChange={(e) => setFormData({ ...formData, imageurl: e.target.value })}
              className="input"
              placeholder="https://..."
            />
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
    </div>
  );
}
