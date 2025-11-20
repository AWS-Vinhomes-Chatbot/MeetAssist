import React from 'react';
import { Header } from '../components/Header';

const AnalyticsPage: React.FC = () => {
  return (
    <div className="min-h-screen bg-gray-50">
      <Header
        title="Analytics"
        subtitle="Analyze chatbot performance and usage"
      />
      <div className="p-6">
        <div className="rounded-lg border bg-white p-6 shadow-sm">
          <p className="text-gray-600">Analytics page - Coming soon</p>
        </div>
      </div>
    </div>
  );
};

export default AnalyticsPage;
