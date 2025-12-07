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

/**
 * Get a single customer by ID
 */
export async function getCustomerById(customerid: number): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'get_customer_by_id',
    customerid
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to get customer');
  }
  
  return response;
}

/**
 * Create a new customer
 */
export async function createCustomer(data: {
  fullname: string;
  email: string;
  phonenumber?: string;
  dateofbirth?: string;
  notes?: string;
}): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'create_customer',
    ...data
  });
  
  return response; // Return full response (includes success and error fields)
}

/**
 * Update an existing customer
 */
export async function updateCustomer(customerid: string, data: {
  fullname?: string;
  email?: string;
  phonenumber?: string;
  dateofbirth?: string;
  notes?: string;
  isdisabled?: boolean;
}): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'update_customer',
    customerid,
    ...data
  });
  
  return response; // Return full response
}

/**
 * Delete a customer (soft delete)
 */
export async function deleteCustomer(customerid: string): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'delete_customer',
    customerid
  });
  
  return response; // Return full response (may include active_appointments, message)
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

// ==================== CONSULTANT CRUD ====================

/**
 * Create a new consultant
 */
export async function createConsultant(data: {
  fullname: string;
  email: string;
  phonenumber?: string;
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
  customerid: string;
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
  customerid?: string;
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

// ==================== CONSULTANT SCHEDULE ====================
export async function getScheduleByConsultant(
  consultantId: number,
  dateFrom?: string,
  dateTo?: string
): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'get_schedule_by_consultant',
    consultant_id: consultantId,
    date_from: dateFrom,
    date_to: dateTo
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to get consultant schedule');
  }
  
  return response;
}

/**
 * Create a new schedule slot for a consultant
 */
export async function createConsultantSchedule(data: {
  consultant_id: number;
  date: string;
  start_time: string;
  end_time: string;
  is_available?: boolean;
}): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'create_consultant_schedule',
    ...data
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to create schedule');
  }
  
  return response;
}

/**
 * Update an existing schedule slot
 */
export async function updateConsultantSchedule(
  schedule_id: number,
  data: {
    date?: string;
    start_time?: string;
    end_time?: string;
    is_available?: boolean;
  }
): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'update_consultant_schedule',
    schedule_id,
    ...data
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to update schedule');
  }
  
  return response;
}

/**
 * Delete a schedule slot
 */
export async function deleteConsultantSchedule(schedule_id: number): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'delete_consultant_schedule',
    schedule_id
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to delete schedule');
  }
  
  return response;
}

/**
 * Generate schedule slots automatically for a consultant
 */
export async function generateConsultantSchedule(data: {
  consultant_id: number;
  date_from: string;
  date_to: string;
  work_start?: string;
  work_end?: string;
  slot_duration?: number;
  exclude_weekends?: boolean;
}): Promise<any> {
  const response = await apiService.post('/admin/execute-sql', {
    action: 'generate_consultant_schedule',
    ...data
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to generate schedule');
  }
  
  return response;
}

// ==================== CONSULTANT ACCOUNT MANAGEMENT ====================
// These functions call the Sync API (outside VPC) to manage Cognito users

/**
 * Call Sync API to manage Consultant Cognito users
 */
async function callSyncApi(action: string, data: Record<string, unknown> = {}): Promise<any> {
  const syncEndpoint = config.syncApiEndpoint;
  if (!syncEndpoint) {
    throw new Error('Sync API endpoint not configured');
  }
  
  const response = await fetch(syncEndpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ action, ...data }),
  });
  
  const result = await response.json();
  
  if (!response.ok || !result.success) {
    throw new Error(result.error || `Sync API failed with status ${response.status}`);
  }
  
  return result;
}

/**
 * Get consultants with Cognito account status
 */
export async function getConsultantsWithAccountStatus(options?: { limit?: number; offset?: number }): Promise<any> {
  // Get consultants from RDS via main API
  const consultantsResponse = await apiService.post('/admin/execute-sql', {
    action: 'get_consultants',
    ...options
  }) as any;
  
  if (!consultantsResponse.success) {
    throw new Error(consultantsResponse.error || 'Failed to get consultants');
  }
  
  // Get Cognito users via Sync API
  try {
    const cognitoUsers = await callSyncApi('list_users');
    
    // Create a map of email -> user info for quick lookup
    const cognitoUserMap = new Map<string, { status: string; enabled: boolean; consultant_id: string | null }>();
    for (const user of cognitoUsers.users || []) {
      if (user.email) {
        cognitoUserMap.set(user.email.toLowerCase(), {
          status: user.status,
          enabled: user.enabled,
          consultant_id: user.consultant_id
        });
      }
    }
    
    // Merge account status with full details
    const consultants = consultantsResponse.consultants.map((c: { email?: string }) => {
      const cognitoUser = c.email ? cognitoUserMap.get(c.email.toLowerCase()) : null;
      return {
        ...c,
        has_cognito_account: !!cognitoUser,
        account_status: cognitoUser ? {
          exists: true,
          status: cognitoUser.status,
          enabled: cognitoUser.enabled
        } : {
          exists: false
        }
      };
    });
    
    return { ...consultantsResponse, consultants };
  } catch (error) {
    console.warn('Could not fetch Cognito users, returning consultants without account status:', error);
    return consultantsResponse;
  }
}

/**
 * Create Cognito account for a consultant
 */
export async function createConsultantAccount(data: {
  email: string;
  consultant_id: number;
  fullname?: string;
  send_email?: boolean;
}): Promise<any> {
  return callSyncApi('create_user', {
    email: data.email,
    consultant_id: data.consultant_id,
    send_invite: data.send_email !== false
  });
}

/**
 * Sync all consultant accounts with Cognito
 * Use this after stack redeploy to recreate all accounts
 */
export async function syncAllConsultantAccounts(): Promise<any> {
  // Get all consultants from RDS
  const consultantsResponse = await apiService.post('/admin/execute-sql', {
    action: 'get_consultants',
    limit: 1000
  }) as any;
  
  if (!consultantsResponse.success) {
    throw new Error(consultantsResponse.error || 'Failed to get consultants');
  }
  
  const results = {
    created: 0,
    already_exists: 0,
    skipped: 0,
    failed: 0,
    errors: [] as string[]
  };
  
  // Create Cognito user for each consultant with email
  for (const consultant of consultantsResponse.consultants || []) {
    if (!consultant.email) {
      results.skipped++;
      continue;
    }
    
    try {
      const result = await callSyncApi('create_user', {
        email: consultant.email,
        consultant_id: consultant.consultantid,
        send_invite: true
      });
      
      if (result.action === 'created') {
        results.created++;
      } else if (result.action === 'updated') {
        results.already_exists++;
      }
    } catch (error) {
      results.failed++;
      results.errors.push(`${consultant.email}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  
  return { success: true, ...results };
}

/**
 * Reset password for a consultant account
 */
export async function resetConsultantPassword(email: string): Promise<any> {
  return callSyncApi('reset_password', { email, send_invite: false });
}

/**
 * Delete Cognito account for a consultant
 */
export async function deleteConsultantAccount(email: string): Promise<any> {
  return callSyncApi('delete_user', { email });
}

/**
 * Get available schedules for a specific consultant
 */


export default apiService;