import { useState, useEffect } from 'react';
import Header from '../components/Header';
import Button from '../components/Button';
import Modal from '../components/Modal';
import { CommunityProgram } from '../types';
import { getPrograms, createProgram, updateProgram, deleteProgram } from '../services/api.service';

export default function ProgramsPage() {
  const [programs, setPrograms] = useState<CommunityProgram[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingProgram, setEditingProgram] = useState<CommunityProgram | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [formData, setFormData] = useState({
    programname: '',
    date: '',
    description: '',
    content: '',
    organizer: '',
    url: '',
    status: 'upcoming'
  });

  useEffect(() => {
    fetchPrograms();
  }, [statusFilter]);

  const fetchPrograms = async () => {
    try {
      setLoading(true);
      const params: Record<string, unknown> = { limit: 100, offset: 0 };
      if (statusFilter) params.status = statusFilter;
      
      const response = await getPrograms(params);
      setPrograms(response.programs || []);
    } catch (error) {
      console.error('Error fetching programs:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = () => {
    setEditingProgram(null);
    setFormData({
      programname: '',
      date: new Date().toISOString().split('T')[0],
      description: '',
      content: '',
      organizer: '',
      url: '',
      status: 'upcoming'
    });
    setIsModalOpen(true);
  };

  const handleEdit = (program: CommunityProgram) => {
    setEditingProgram(program);
    setFormData({
      programname: program.programname,
      date: program.date,
      description: program.description || '',
      content: program.content || '',
      organizer: program.organizer || '',
      url: program.url || '',
      status: program.status
    });
    setIsModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (editingProgram) {
        await updateProgram(editingProgram.programid, formData);
      } else {
        await createProgram(formData);
      }
      setIsModalOpen(false);
      fetchPrograms();
    } catch (error) {
      console.error('Error saving program:', error);
      alert('Failed to save program');
    }
  };

  const handleDelete = async (programid: number) => {
    if (!globalThis.confirm('Are you sure you want to delete this program?')) {
      return;
    }
    try {
      await deleteProgram(programid);
      fetchPrograms();
    } catch (error) {
      console.error('Error deleting program:', error);
      alert('Failed to delete program');
    }
  };

  const getStatusBadge = (status: string) => {
    const statusColors: Record<string, string> = {
      upcoming: 'badge-info',
      ongoing: 'badge-success',
      completed: 'badge-neutral'
    };
    return statusColors[status] || 'badge-neutral';
  };

  return (
    <div className="min-h-screen">
      <Header 
        title="Quản lý Chương trình Cộng đồng" 
        subtitle="Manage community programs and events"
        actions={
          <Button onClick={handleCreate} icon="➕">
            Add Program
          </Button>
        }
      />

      <div className="p-4 sm:p-6 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Total: <span className="font-medium text-gray-900 dark:text-white">{programs.length}</span> programs
          </p>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="input w-full sm:w-auto sm:min-w-[150px]"
          >
            <option value="">All Status</option>
            <option value="upcoming">Upcoming</option>
            <option value="ongoing">Ongoing</option>
            <option value="completed">Completed</option>
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
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">Program Name</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300 hidden md:table-cell">Date</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300 hidden lg:table-cell">Organizer</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300 hidden xl:table-cell">Description</th>
                    <th className="px-4 py-3 text-left font-semibold text-gray-600 dark:text-gray-300">Status</th>
                    <th className="px-4 py-3 text-right font-semibold text-gray-600 dark:text-gray-300">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                  {programs.map((program) => (
                    <tr key={program.programid} className="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                        {program.programid}
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-medium text-gray-900 dark:text-white">
                          {program.programname}
                        </div>
                        {program.url && (
                          <a 
                            href={program.url} 
                            target="_blank" 
                            rel="noopener noreferrer"
                            className="text-xs text-primary-600 dark:text-primary-400 hover:underline"
                          >
                            View Link →
                          </a>
                        )}
                      </td>
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400 hidden md:table-cell">
                        {program.date}
                      </td>
                      <td className="px-4 py-3 text-gray-500 dark:text-gray-400 hidden lg:table-cell">
                        {program.organizer || '-'}
                      </td>
                      <td className="px-4 py-3 hidden xl:table-cell">
                        <div className="max-w-[200px] truncate text-gray-500 dark:text-gray-400">
                          {program.description || '-'}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`badge ${getStatusBadge(program.status)}`}>
                          {program.status}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => handleEdit(program)}
                            className="p-2 rounded-lg text-primary-600 dark:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors"
                            title="Edit"
                          >
                            ✏️
                          </button>
                          <button
                            onClick={() => handleDelete(program.programid)}
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
        title={editingProgram ? 'Edit Program' : 'Add New Program'}
        size="lg"
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              Program Name *
            </label>
            <input
              type="text"
              required
              value={formData.programname}
              onChange={(e) => setFormData({ ...formData, programname: e.target.value })}
              className="input"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                Date *
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
                Status *
              </label>
              <select
                required
                value={formData.status}
                onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                className="input"
              >
                <option value="upcoming">Upcoming</option>
                <option value="ongoing">Ongoing</option>
                <option value="completed">Completed</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              Organizer
            </label>
            <input
              type="text"
              value={formData.organizer}
              onChange={(e) => setFormData({ ...formData, organizer: e.target.value })}
              className="input"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              Program URL
            </label>
            <input
              type="url"
              value={formData.url}
              onChange={(e) => setFormData({ ...formData, url: e.target.value })}
              placeholder="https://..."
              className="input"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              Description
            </label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              rows={2}
              maxLength={255}
              className="input resize-none"
            />
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Max 255 characters</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
              Content (Detailed Information)
            </label>
            <textarea
              value={formData.content}
              onChange={(e) => setFormData({ ...formData, content: e.target.value })}
              rows={4}
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
              {editingProgram ? 'Update' : 'Create'}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
