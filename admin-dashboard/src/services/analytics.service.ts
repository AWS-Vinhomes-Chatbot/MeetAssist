import { apiService } from './api.service';
import { awsConfig } from '@/aws-exports';
import type {
  AnalyticsMetrics,
  DailyAnalytics,
  TopQuery,
  OverviewStats,
  ApiResponse,
} from '@/types';

class AnalyticsService {
  /**
   * Get overview statistics
   */
  async getOverviewStats(): Promise<ApiResponse<OverviewStats>> {
    return apiService.post<OverviewStats>(awsConfig.api.adminPath, {
      action: 'overview_stats',
    });
  }

  /**
   * Get analytics metrics for date range
   */
  async getAnalytics(
    startDate: string,
    endDate: string
  ): Promise<ApiResponse<AnalyticsMetrics>> {
    return apiService.post<AnalyticsMetrics>(awsConfig.api.adminPath, {
      action: 'analytics',
      start_date: startDate,
      end_date: endDate,
    });
  }

  /**
   * Get daily analytics for date range
   */
  async getDailyAnalytics(
    startDate: string,
    endDate: string
  ): Promise<ApiResponse<DailyAnalytics[]>> {
    return apiService.post<DailyAnalytics[]>(awsConfig.api.adminPath, {
      action: 'daily_analytics',
      start_date: startDate,
      end_date: endDate,
    });
  }

  /**
   * Get top user queries
   */
  async getTopQueries(
    startDate: string,
    endDate: string,
    limit: number = 10
  ): Promise<ApiResponse<TopQuery[]>> {
    return apiService.post<TopQuery[]>(awsConfig.api.adminPath, {
      action: 'top_queries',
      start_date: startDate,
      end_date: endDate,
      limit,
    });
  }

  /**
   * Get trend data for last N days
   */
  async getTrendData(days: number = 7): Promise<ApiResponse<DailyAnalytics[]>> {
    const endDate = new Date();
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - days);

    return this.getDailyAnalytics(
      startDate.toISOString().split('T')[0],
      endDate.toISOString().split('T')[0]
    );
  }
}

export const analyticsService = new AnalyticsService();
export default analyticsService;
