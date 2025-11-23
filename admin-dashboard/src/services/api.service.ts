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
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || data.message || 'API request failed');
      }

      return {
        success: true,
        data: data.data || data,
        message: data.message,
      };
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

// ==================== DATABASE ADMIN FUNCTIONS ====================

/**
 * Execute raw SQL query
 */
export async function executeSql(sql: string): Promise<any> {
  const response = await apiService.post('/admin', {
    action: 'execute_sql',
    sql
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to execute SQL');
  }
  
  return response.data;
}

/**
 * Get list of all tables
 */
export async function getTables(): Promise<any> {
  const response = await apiService.post('/admin', {
    action: 'get_tables'
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to get tables');
  }
  
  return response.data;
}

/**
 * Get schema for a specific table
 */
export async function getTableSchema(tableName: string): Promise<any> {
  const response = await apiService.post('/admin', {
    action: 'get_table_schema',
    table_name: tableName
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to get table schema');
  }
  
  return response.data;
}

/**
 * Get database statistics
 */
export async function getDatabaseStats(): Promise<any> {
  const response = await apiService.post('/admin', {
    action: 'get_stats'
  });
  
  if (!response.success) {
    throw new Error(response.error || 'Failed to get database stats');
  }
  
  return response.data;
}

export default apiService;