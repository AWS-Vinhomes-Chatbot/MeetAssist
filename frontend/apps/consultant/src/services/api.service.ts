import { config } from '../aws-exports';
import { authService } from './auth.service';

class ApiService {
  private getHeaders(): HeadersInit {
    // Cognito Authorizer requires id_token, not access_token
    const token = authService.getIdToken();
    return {
      'Content-Type': 'application/json',
      ...(token && { 'Authorization': `Bearer ${token}` })
    };
  }

  private async request<T>(action: string, params: Record<string, unknown> = {}): Promise<T> {
    // API endpoint is: {apiEndpoint}admin/execute-sql
    const apiUrl = config.apiEndpoint.endsWith('/') 
      ? `${config.apiEndpoint}admin/execute-sql`
      : `${config.apiEndpoint}/admin/execute-sql`;
      
    const response = await fetch(apiUrl, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify({ action, ...params })
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Request failed' }));
      throw new Error(error.error || `Request failed with status ${response.status}`);
    }

    return response.json();
  }

  // Get consultant by email (to map Cognito user to consultant_id)
  async getConsultantByEmail(email: string) {
    return this.request<{
      consultantid: number;
      fullname: string;
      email: string;
      specialties: string;
    }>('get_consultant_by_email', { email });
  }

  // Get my schedule
  async getMySchedule(consultantId: number, params: {
    date_from?: string;
    date_to?: string;
    is_available?: boolean;
    limit?: number;
    offset?: number;
  } = {}) {
    return this.request<{
      schedules: Array<{
        scheduleid: number;
        consultantid: number;
        date: string;
        starttime: string;
        endtime: string;
        isavailable: boolean;
      }>;
      total: number;
    }>('get_my_schedule', { consultant_id: consultantId, ...params });
  }

  // Get my appointments
  async getMyAppointments(consultantId: number, params: {
    status?: string;
    date_from?: string;
    date_to?: string;
    limit?: number;
    offset?: number;
  } = {}) {
    return this.request<{
      appointments: Array<{
        appointmentid: number;
        date: string;
        time: string;
        duration: number;
        status: string;
        description: string;
        customer_name: string;
        customer_email: string;
        customer_phone: string;
      }>;
      total: number;
    }>('get_my_appointments', { consultant_id: consultantId, ...params });
  }

  // Confirm appointment
  async confirmAppointment(consultantId: number, appointmentId: number) {
    return this.request<{
      success: boolean;
      message: string;
      error?: string;
    }>('confirm_appointment', { consultant_id: consultantId, appointment_id: appointmentId });
  }

  // Deny/Cancel appointment
  async denyAppointment(consultantId: number, appointmentId: number, reason?: string) {
    return this.request<{
      success: boolean;
      message: string;
      error?: string;
    }>('deny_appointment', { consultant_id: consultantId, appointment_id: appointmentId, reason });
  }
}

export const apiService = new ApiService();
