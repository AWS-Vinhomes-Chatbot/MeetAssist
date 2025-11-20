import { apiService } from './api.service';
import { awsConfig } from '@/aws-exports';
import type { Conversation, ConversationFilters, ApiResponse } from '@/types';

class ConversationService {
  /**
   * Query conversations with filters
   */
  async queryConversations(
    filters: ConversationFilters
  ): Promise<ApiResponse<Conversation[]>> {
    return apiService.post<Conversation[]>(awsConfig.api.adminPath, {
      action: 'query_conversations',
      filters: {
        start_date: filters.startDate,
        end_date: filters.endDate,
        user_id: filters.userId,
        status: filters.status,
      },
    });
  }

  /**
   * Get conversation by ID
   */
  async getConversationById(
    conversationId: string
  ): Promise<ApiResponse<Conversation>> {
    return apiService.post<Conversation>(awsConfig.api.adminPath, {
      action: 'get_conversation',
      conversation_id: conversationId,
    });
  }

  /**
   * Export conversations to CSV
   */
  async exportToCSV(filters: ConversationFilters): Promise<ApiResponse<string>> {
    const response = await this.queryConversations(filters);
    
    if (!response.success || !response.data) {
      return {
        success: false,
        error: response.error || 'Failed to fetch data for export',
      };
    }

    try {
      const csv = this.convertToCSV(response.data);
      return {
        success: true,
        data: csv,
      };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'CSV conversion failed',
      };
    }
  }

  /**
   * Convert conversations to CSV format
   */
  private convertToCSV(conversations: Conversation[]): string {
    if (conversations.length === 0) {
      return '';
    }

    // Headers
    const headers = [
      'Conversation ID',
      'User ID',
      'Timestamp',
      'User Query',
      'SQL Generated',
      'Query Results',
      'Response',
      'Status',
      'Execution Time (ms)',
    ];

    // Rows
    const rows = conversations.map((conv) => [
      conv.conversation_id,
      conv.user_id,
      conv.timestamp,
      `"${conv.user_query.replace(/"/g, '""')}"`,
      `"${conv.sql_generated.replace(/"/g, '""')}"`,
      `"${conv.query_results.replace(/"/g, '""')}"`,
      `"${conv.response.replace(/"/g, '""')}"`,
      conv.status,
      conv.execution_time_ms.toString(),
    ]);

    // Combine
    return [headers.join(','), ...rows.map((row) => row.join(','))].join('\n');
  }

  /**
   * Download CSV file
   */
  downloadCSV(csv: string, filename: string = 'conversations.csv'): void {
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.visibility = 'hidden';
    
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    URL.revokeObjectURL(url);
  }
}

export const conversationService = new ConversationService();
export default conversationService;
