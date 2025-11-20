import { useState, useEffect } from 'react';
import { Header } from '../components/Header';
import { StatCard } from '../components/Card';
import { Button } from '../components/Button';

const OverviewPage: React.FC = () => {
  const [loading, setLoading] = useState(false);

  const stats = {
    totalConversations: '1,234',
    successRate: '94.5%',
    activeUsers: '456',
    avgResponseTime: '1.2s',
  };

  const handleRefresh = () => {
    setLoading(true);
    setTimeout(() => setLoading(false), 1000);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Header
        title="Overview"
        subtitle="Welcome back! Here's what's happening today."
        actions={
          <Button onClick={handleRefresh} loading={loading} icon="🔄">
            Refresh
          </Button>
        }
      />

      <div className="p-6">
        {/* Stats Grid */}
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
          <StatCard
            title="Total Conversations"
            value={stats.totalConversations}
            icon="💬"
            change="+12.5%"
            changeType="positive"
            color="blue"
          />
          <StatCard
            title="Success Rate"
            value={stats.successRate}
            icon="✅"
            change="+2.1%"
            changeType="positive"
            color="green"
          />
          <StatCard
            title="Active Users"
            value={stats.activeUsers}
            icon="👥"
            change="+8.3%"
            changeType="positive"
            color="orange"
          />
          <StatCard
            title="Avg Response Time"
            value={stats.avgResponseTime}
            icon="⚡"
            change="-0.3s"
            changeType="positive"
            color="purple"
          />
        </div>

        {/* Placeholder for charts */}
        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="rounded-lg border bg-white p-6 shadow-sm">
            <h3 className="mb-4 text-lg font-semibold">Conversations Trend</h3>
            <div className="flex h-64 items-center justify-center bg-gray-50 text-gray-500">
              Chart placeholder - Install and configure Chart.js
            </div>
          </div>
          
          <div className="rounded-lg border bg-white p-6 shadow-sm">
            <h3 className="mb-4 text-lg font-semibold">Status Distribution</h3>
            <div className="flex h-64 items-center justify-center bg-gray-50 text-gray-500">
              Chart placeholder - Install and configure Chart.js
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default OverviewPage;
