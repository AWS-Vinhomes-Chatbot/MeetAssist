import React from 'react';
import { Header } from '../components/Header';

const AnalyticsPage: React.FC = () => {
  return (
    <div className="min-h-screen">
      <Header
        title="Analytics"
        subtitle="Analyze chatbot performance and usage"
      />
      <div className="p-4 sm:p-6">
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-8 text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-gray-100 dark:bg-gray-700 mb-4">
            <span className="text-3xl">📈</span>
          </div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Coming Soon</h3>
          <p className="text-gray-500 dark:text-gray-400">Analytics page is under development</p>
        </div>
      </div>
    </div>
  );
};

export default AnalyticsPage;
