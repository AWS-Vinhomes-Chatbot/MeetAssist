import { useState, useEffect } from 'react';
import { apiService } from '../services/api.service';
import { Calendar, Clock, Loader2, ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react';
import { format, startOfWeek, endOfWeek, addWeeks, subWeeks, parseISO, isToday } from 'date-fns';

interface Schedule {
  scheduleid: number;
  consultantid: number;
  date: string;
  starttime: string;
  endtime: string;
  isavailable: boolean;
}

interface Props {
  consultantId: number;
}

export default function SchedulePage({ consultantId }: Props) {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [currentWeek, setCurrentWeek] = useState(new Date());
  const [error, setError] = useState<string | null>(null);

  const weekStart = startOfWeek(currentWeek, { weekStartsOn: 1 });
  const weekEnd = endOfWeek(currentWeek, { weekStartsOn: 1 });

  useEffect(() => {
    if (consultantId) {
      loadSchedule();
    }
  }, [consultantId, currentWeek]);

  const loadSchedule = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiService.getMySchedule(consultantId, {
        date_from: format(weekStart, 'yyyy-MM-dd'),
        date_to: format(weekEnd, 'yyyy-MM-dd'),
        limit: 100
      });
      setSchedules(data.schedules);
    } catch (err) {
      console.error('Failed to load schedule:', err);
      setError('Không thể tải lịch làm việc');
    } finally {
      setIsLoading(false);
    }
  };

  const groupByDate = (items: Schedule[]): Record<string, Schedule[]> => {
    const grouped: Record<string, Schedule[]> = {};
    for (const item of items) {
      if (!grouped[item.date]) grouped[item.date] = [];
      grouped[item.date].push(item);
    }
    for (const date of Object.keys(grouped)) {
      grouped[date].sort((a, b) => a.starttime.localeCompare(b.starttime));
    }
    return grouped;
  };

  const groupedSchedules = groupByDate(schedules);
  const dates = Object.keys(groupedSchedules).sort((a, b) => a.localeCompare(b));

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
          <button onClick={loadSchedule} className="mt-4 text-teal-500 hover:underline">
            Thử lại
          </button>
        </div>
      );
    }

    if (dates.length === 0) {
      return (
        <div className="bg-white rounded-lg shadow p-12 text-center">
          <Calendar className="w-16 h-16 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-gray-700">Không tìm thấy lịch làm việc</h3>
          <p className="text-gray-500 mt-2">Chưa có khung giờ nào cho tuần này</p>
        </div>
      );
    }

    return (
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {dates.map(date => {
          const dateObj = parseISO(date);
          const daySchedules = groupedSchedules[date];
          const availableCount = daySchedules.filter(s => s.isavailable).length;

          return (
            <div
              key={date}
              className={`bg-white rounded-lg shadow overflow-hidden ${
                isToday(dateObj) ? 'ring-2 ring-teal-500' : ''
              }`}
            >
              <div className={`px-4 py-3 ${isToday(dateObj) ? 'bg-teal-500 text-white' : 'bg-gray-50'}`}>
                <div className="flex items-center justify-between">
                  <div>
                    <p className={`font-semibold ${isToday(dateObj) ? 'text-white' : 'text-gray-800'}`}>
                      {format(dateObj, 'EEEE')}
                    </p>
                    <p className={`text-sm ${isToday(dateObj) ? 'text-teal-100' : 'text-gray-500'}`}>
                      {format(dateObj, 'MMMM d, yyyy')}
                    </p>
                  </div>
                  <span className={`text-sm px-2 py-1 rounded ${
                    isToday(dateObj) ? 'bg-teal-400 text-white' : 'bg-gray-200 text-gray-600'
                  }`}>
                    {availableCount} khả dụng
                  </span>
                </div>
              </div>

              <div className="p-4 space-y-2 max-h-80 overflow-y-auto">
                {daySchedules.map(slot => (
                  <div
                    key={slot.scheduleid}
                    className={`flex items-center gap-3 p-3 rounded-lg ${
                      slot.isavailable
                        ? 'bg-green-50 border border-green-200'
                        : 'bg-gray-100 border border-gray-200'
                    }`}
                  >
                    <Clock className={`w-4 h-4 ${slot.isavailable ? 'text-green-500' : 'text-gray-400'}`} />
                    <span className={`font-medium ${slot.isavailable ? 'text-green-700' : 'text-gray-500'}`}>
                      {slot.starttime} - {slot.endtime}
                    </span>
                    {!slot.isavailable && (
                      <span className="text-xs text-gray-500 ml-auto">Đã đặt</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-2xl font-bold text-gray-800">Lịch Làm Việc</h2>
          <p className="text-gray-500 mt-1">Các khung giờ khả dụng của bạn</p>
        </div>

        <div className="flex items-center gap-4">
          <button
            onClick={() => setCurrentWeek(subWeeks(currentWeek, 1))}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ChevronLeft className="w-5 h-5 text-gray-600" />
          </button>

          <div className="text-center min-w-[200px]">
            <p className="font-semibold text-gray-800">
              {format(weekStart, 'MMM d')} - {format(weekEnd, 'MMM d, yyyy')}
            </p>
          </div>

          <button
            onClick={() => setCurrentWeek(addWeeks(currentWeek, 1))}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ChevronRight className="w-5 h-5 text-gray-600" />
          </button>

          <button
            onClick={loadSchedule}
            className="flex items-center gap-2 px-4 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Làm Mới
          </button>
        </div>
      </div>

      {/* Content */}
      {renderContent()}
    </div>
  );
}
