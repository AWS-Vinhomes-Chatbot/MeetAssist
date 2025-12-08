/**
 * Utility functions for formatting dates, times, and status in Vietnamese
 */

/**
 * Format date to Vietnamese format
 * @param dateStr - Date string (YYYY-MM-DD)
 * @returns Formatted date string (DD/MM/YYYY hoặc Thứ X, DD/MM/YYYY)
 */
export const formatDateVN = (dateStr: string | undefined, includeWeekday = false): string => {
  if (!dateStr) return '';
  
  try {
    const date = new Date(dateStr);
    const day = String(date.getDate()).padStart(2, '0');
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const year = date.getFullYear();
    
    if (includeWeekday) {
      const weekdays = ['Chủ Nhật', 'Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy'];
      const weekday = weekdays[date.getDay()];
      return `${weekday}, ${day}/${month}/${year}`;
    }
    
    return `${day}/${month}/${year}`;
  } catch {
    return dateStr;
  }
};

/**
 * Format time to Vietnamese format
 * @param timeStr - Time string (HH:MM or HH:MM:SS)
 * @returns Formatted time string
 */
export const formatTimeVN = (timeStr: string | undefined): string => {
  if (!timeStr) return '';
  
  // Extract HH:MM from HH:MM:SS if needed
  const parts = timeStr.split(':');
  return `${parts[0]}:${parts[1]}`;
};

/**
 * Format datetime to Vietnamese format
 * @param dateStr - Date string
 * @param timeStr - Time string
 * @returns Combined formatted datetime
 */
export const formatDateTimeVN = (dateStr: string | undefined, timeStr: string | undefined): string => {
  const date = formatDateVN(dateStr);
  const time = formatTimeVN(timeStr);
  return date && time ? `${date} lúc ${time}` : date || time;
};

/**
 * Translate appointment status to Vietnamese
 */
export const statusToVietnamese = (status: string): string => {
  const statusMap: Record<string, string> = {
    'pending': 'Chờ Xác Nhận',
    'confirmed': 'Đã Xác Nhận',
    'completed': 'Hoàn Thành',
    'cancelled': 'Đã Hủy',
    'canceled': 'Đã Hủy', // Handle both spellings
  };
  
  return statusMap[status.toLowerCase()] || status;
};

/**
 * Get status badge color classes
 */
export const getStatusBadgeClass = (status: string): string => {
  const statusLower = status.toLowerCase();
  
  switch (statusLower) {
    case 'pending':
      return 'bg-yellow-100 text-yellow-800 border-yellow-200';
    case 'confirmed':
      return 'bg-green-100 text-green-800 border-green-200';
    case 'completed':
      return 'bg-blue-100 text-blue-800 border-blue-200';
    case 'cancelled':
    case 'canceled':
      return 'bg-red-100 text-red-800 border-red-200';
    default:
      return 'bg-gray-100 text-gray-800 border-gray-200';
  }
};

/**
 * Format duration in minutes to Vietnamese
 */
export const formatDurationVN = (minutes: number): string => {
  if (minutes < 60) {
    return `${minutes} phút`;
  }
  
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  
  if (remainingMinutes === 0) {
    return `${hours} giờ`;
  }
  
  return `${hours} giờ ${remainingMinutes} phút`;
};
