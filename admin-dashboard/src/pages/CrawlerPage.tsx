import { useState } from 'react';
import { Header } from '../components/Header';
import { Button } from '../components/Button';
import { crawlerService } from '../services/crawler.service';

const CrawlerPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string>('UNKNOWN');
  const [message, setMessage] = useState<string>('Ready to sync data');

  const handleStartCrawler = async () => {
    setLoading(true);
    setMessage('Starting crawler...');
    
    const response = await crawlerService.startCrawler();
    
    if (response.success) {
      setMessage(response.data?.message || 'Crawler started successfully');
      setStatus('RUNNING');
    } else {
      setMessage(`Error: ${response.error}`);
      setStatus('FAILED');
    }
    
    setLoading(false);
  };

  const handleCheckStatus = async () => {
    setLoading(true);
    
    const response = await crawlerService.getCrawlerStatus();
    
    if (response.success && response.data) {
      setStatus(response.data.state);
      setMessage(response.data.message || `Crawler status: ${response.data.state}`);
    } else {
      setMessage(`Error: ${response.error}`);
    }
    
    setLoading(false);
  };

  const getStatusColor = () => {
    switch (status) {
      case 'RUNNING':
        return 'bg-blue-100 text-blue-800';
      case 'SUCCEEDED':
        return 'bg-green-100 text-green-800';
      case 'FAILED':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Header
        title="Data Sync"
        subtitle="Manage AWS Glue Crawler for data synchronization"
      />

      <div className="p-6">
        <div className="mx-auto max-w-3xl">
          <div className="rounded-lg border bg-white p-6 shadow-sm">
            <div className="mb-6 flex items-center justify-between">
              <h3 className="text-xl font-semibold">🔄 AWS Glue Crawler</h3>
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-gray-600">Status:</span>
                <span className={`rounded-full px-3 py-1 text-sm font-medium ${getStatusColor()}`}>
                  {status}
                </span>
              </div>
            </div>

            <div className="mb-6 rounded-lg bg-gray-50 p-4">
              <p className="text-sm text-gray-700">
                The Glue Crawler scans conversation data from S3 and updates the Glue Data Catalog,
                enabling Athena to query the latest data.
              </p>
              <ul className="mt-3 space-y-1 text-sm text-gray-600">
                <li>✓ Automatically discovers schema changes</li>
                <li>✓ Creates partitions for efficient querying</li>
                <li>✓ Updates metadata for Athena access</li>
              </ul>
            </div>

            <div className="mb-6 flex gap-3">
              <Button
                onClick={handleStartCrawler}
                loading={loading}
                icon="▶️"
                variant="primary"
                size="lg"
              >
                Start Crawler
              </Button>
              <Button
                onClick={handleCheckStatus}
                loading={loading}
                icon="🔍"
                variant="secondary"
                size="lg"
              >
                Check Status
              </Button>
            </div>

            <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
              <p className="font-mono text-sm text-gray-700">{message}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CrawlerPage;
