import { apiService } from './api.service';
import { config } from '../aws-exports';
import type { CrawlerStatus, ApiResponse } from '../types';

class CrawlerService {
  /**
   * Trigger Glue Crawler
   */
  async startCrawler(): Promise<ApiResponse<{ message: string }>> {
    return apiService.post<{ message: string }>(config.api.crawlerPath, {
      action: 'start_crawler',
    });
  }

  /**
   * Get crawler status
   */
  async getCrawlerStatus(): Promise<ApiResponse<CrawlerStatus>> {
    return apiService.post<CrawlerStatus>(config.api.crawlerPath, {
      action: 'get_status',
    });
  }

  /**
   * Check if crawler is running
   */
  async isRunning(): Promise<boolean> {
    const response = await this.getCrawlerStatus();
    return response.success && response.data?.state === 'RUNNING';
  }

  /**
   * Wait for crawler to complete (polling)
   */
  async waitForCompletion(
    onProgress?: (status: CrawlerStatus) => void,
    maxAttempts: number = 60,
    intervalMs: number = 5000
  ): Promise<ApiResponse<CrawlerStatus>> {
    let attempts = 0;

    while (attempts < maxAttempts) {
      const response = await this.getCrawlerStatus();

      if (!response.success || !response.data) {
        return response;
      }

      const status = response.data;

      if (onProgress) {
        onProgress(status);
      }

      // Check if completed
      if (
        status.state === 'SUCCEEDED' ||
        status.state === 'FAILED' ||
        status.state === 'STOPPED'
      ) {
        return response;
      }

      // Wait before next poll
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
      attempts++;
    }

    return {
      success: false,
      error: 'Crawler status check timeout',
    };
  }
}

export const crawlerService = new CrawlerService();
export default crawlerService;
