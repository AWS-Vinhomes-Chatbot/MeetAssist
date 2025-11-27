import { authService } from './auth.service';
import { config } from '../aws-exports';
import type { ApiResponse } from '../types';

class ApiService {
  private baseUrl: string;

  constructor() {
    this.baseUrl = config.api.endpoint;
  }

  /**
   * Make authenticated API request
   */
  private async request<T>(
    path: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    try {
      // Get auth token
      const idToken = authService.getIdToken();
      
      // Prepare headers
      const headers = new Headers(options.headers);
      if (idToken) {
        headers.set('Authorization', `Bearer ${idToken}`);
      }
      headers.set('Content-Type', 'application/json');

      // Make request
      const response = await fetch(`${this.baseUrl}${path}`, {
        ...options,
        headers,
      });

      // Parse response
      let data = await response.json();
      
      console.log('Raw API response:', data);
      
      // Handle API Gateway string body format
      if (typeof data.body === 'string') {
        console.log('Parsing body string...');
        data = JSON.parse(data.body);
        console.log('Parsed data:', data);
      }

      if (!response.ok) {
        throw new Error(data.error || data.message || 'API request failed');
      }

      const result = {
        success: true,
        ...data, // ← Spread tất cả fields từ data gốc (message, rows_returned, rows_affected, v.v.)
      };
      
      console.log('Final result:', result);
      return result;
    } catch (error) {
      console.error('API request error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error',
      };
    }
  }

  /**
   * GET request
   */
  async get<T>(path: string): Promise<ApiResponse<T>> {
    return this.request<T>(path, { method: 'GET' });
  }

  /**
   * POST request
   */
  async post<T>(path: string, body?: unknown): Promise<ApiResponse<T>> {
    return this.request<T>(path, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  /**
   * PUT request
   */
  async put<T>(path: string, body?: unknown): Promise<ApiResponse<T>> {
    return this.request<T>(path, {
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  /**
   * DELETE request
   */
  async delete<T>(path: string): Promise<ApiResponse<T>> {
    return this.request<T>(path, { method: 'DELETE' });
  }
}

export const apiService = new ApiService();

// ==================== OVERVIEW & DASHBOARD ====================

/**
 * Get overview statistics for dashboard
 */
export async function getOverviewStats(): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'get_overview_stats'
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to get overview stats');
  }
  
  return response;
}

// ==================== CUSTOMERS ====================

/**
 * Get customers list
 */
export async function getCustomers(options?: { limit?: number; offset?: number; search?: string }): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'get_customers',
    ...options
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to get customers');
  }
  
  return response;
}

// ==================== CONSULTANTS ====================

/**
 * Get consultants list
 */
export async function getConsultants(options?: { limit?: number; offset?: number }): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'get_consultants',
    ...options
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to get consultants');
  }
  
  return response;
}

// ==================== APPOINTMENTS ====================

/**
 * Get appointments list
 */
export async function getAppointments(options?: { limit?: number; offset?: number; status?: string }): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'get_appointments',
    ...options
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to get appointments');
  }
  
  return response;
}

// ==================== COMMUNITY PROGRAMS ====================

/**
 * Get community programs list
 */
export async function getPrograms(options?: { limit?: number; offset?: number; status?: string }): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'get_programs',
    ...options
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to get programs');
  }
  
  return response;
}

// ==================== DATABASE ADMIN FUNCTIONS ====================

/**
 * Get list of all tables
 */
export async function getTables(): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'get_tables'
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to get tables');
  }
  
  return response;
}

/**
 * Get schema for a specific table
 */
export async function getTableSchema(tableName: string): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'get_table_schema',
    table_name: tableName
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to get table schema');
  }
  
  return response;
}

/**
 * Get database statistics
 */
export async function getDatabaseStats(): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'get_stats'
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to get database stats');
  }
  
  return response;
}

// ==================== CONSULTANT CRUD ====================

/**
 * Create a new consultant
 */
export async function createConsultant(data: {
  fullname: string;
  email: string;
  phonenumber?: string;
  imageurl?: string;
  specialties?: string;
  qualifications?: string;
  joindate?: string;
}): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'create_consultant',
    ...data
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to create consultant');
  }
  
  return response;
}

/**
 * Update an existing consultant
 */
export async function updateConsultant(consultantid: number, data: {
  fullname?: string;
  email?: string;
  phonenumber?: string;
  imageurl?: string;
  specialties?: string;
  qualifications?: string;
  joindate?: string;
  isdisabled?: boolean;
}): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'update_consultant',
    consultantid,
    ...data
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to update consultant');
  }
  
  return response;
}

/**
 * Delete a consultant (soft delete)
 */
export async function deleteConsultant(consultantid: number): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'delete_consultant',
    consultantid
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to delete consultant');
  }
  
  return response;
}

// ==================== APPOINTMENT CRUD ====================

/**
 * Create a new appointment
 */
export async function createAppointment(data: {
  consultantid: number;
  customerid: number;
  date: string;
  time: string;
  duration?: number;
  meetingurl?: string;
  status?: string;
  description?: string;
}): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'create_appointment',
    ...data
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to create appointment');
  }
  
  return response;
}

/**
 * Update an existing appointment
 */
export async function updateAppointment(appointmentid: number, data: {
  consultantid?: number;
  customerid?: number;
  date?: string;
  time?: string;
  duration?: number;
  meetingurl?: string;
  status?: string;
  description?: string;
}): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'update_appointment',
    appointmentid,
    ...data
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to update appointment');
  }
  
  return response;
}

/**
 * Delete an appointment
 */
export async function deleteAppointment(appointmentid: number): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'delete_appointment',
    appointmentid
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to delete appointment');
  }
  
  return response;
}

// ==================== COMMUNITY PROGRAM CRUD ====================

/**
 * Create a new community program
 */
export async function createProgram(data: {
  programname: string;
  date: string;
  description?: string;
  content?: string;
  organizer?: string;
  url?: string;
  status?: string;
}): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'create_program',
    ...data
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to create program');
  }
  
  return response;
}

/**
 * Update an existing community program
 */
export async function updateProgram(programid: number, data: {
  programname?: string;
  date?: string;
  description?: string;
  content?: string;
  organizer?: string;
  url?: string;
  status?: string;
  isdisabled?: boolean;
}): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'update_program',
    programid,
    ...data
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to update program');
  }
  
  return response;
}

/**
 * Delete a community program (soft delete)
 */
export async function deleteProgram(programid: number): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'delete_program',
    programid
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to delete program');
  }
  
  return response;
}

export default apiService;