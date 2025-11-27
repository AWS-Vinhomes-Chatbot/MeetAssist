// Type definitions for the admin dashboard

export interface User {
  email: string;
  sub: string;
  email_verified?: boolean;
}

export interface AuthTokens {
  accessToken: string;
  idToken: string;
  refreshToken?: string;
}

export interface Conversation {
  conversation_id: string;
  user_id: string;
  timestamp: string;
  user_query: string;
  sql_generated: string;
  query_results: string;
  response: string;
  status: 'success' | 'error' | 'timeout';
  execution_time_ms: number;
}

export interface ConversationFilters {
  startDate?: string;
  endDate?: string;
  userId?: string;
  status?: string;
}

export interface AnalyticsMetrics {
  totalQueries: number;
  uniqueUsers: number;
  successRate: number;
  avgExecutionTime: number;
}

export interface DailyAnalytics {
  date: string;
  total: number;
  success: number;
  error: number;
  avgTime: number;
}

export interface TopQuery {
  query: string;
  count: number;
  avgTime: number;
}

export interface OverviewStats {
  totalConversations: number;
  successRate: number;
  activeUsers: number;
  avgResponseTime: number;
  trends: {
    conversationsChange: number;
    successRateChange: number;
    usersChange: number;
    timeChange: number;
  };
}

export interface CrawlerStatus {
  state: 'READY' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'STOPPED' | 'UNKNOWN';
  lastRunTime?: string;
  duration?: number;
  tablesUpdated?: number;
  message?: string;
}

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}

export interface ChartData {
  labels: string[];
  datasets: {
    label: string;
    data: number[];
    backgroundColor?: string | string[];
    borderColor?: string | string[];
    borderWidth?: number;
  }[];
}

// ==================== CRUD ENTITIES ====================

export interface Consultant {
  consultantid: number;
  fullname: string;
  email: string;
  phonenumber?: string;
  imageurl?: string;
  specialties?: string;
  qualifications?: string;
  joindate?: string;
  createdat?: string;
  isdisabled?: boolean;
}

export interface Appointment {
  appointmentid: number;
  consultantid: number;
  customerid: number;
  date: string;
  time: string;
  duration: number;
  meetingurl?: string;
  status: 'pending' | 'confirmed' | 'completed' | 'cancelled';
  description?: string;
  createdat?: string;
  updatedat?: string;
}

export interface CommunityProgram {
  programid: number;
  programname: string;
  date: string;
  description?: string;
  content?: string;
  organizer?: string;
  url?: string;
  isdisabled?: boolean;
  status: 'upcoming' | 'ongoing' | 'completed';
  createdat?: string;
}

export interface Customer {
  customerid: number;
  fullname: string;
  email: string;
  phonenumber?: string;
  dateofbirth?: string;
  createdat?: string;
  isdisabled?: boolean;
  notes?: string;
}
