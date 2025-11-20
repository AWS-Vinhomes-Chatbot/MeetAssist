import React from 'react';
import { Header } from '../components/Header';

const ConversationsPage: React.FC = () => {
  return (
    <div className="min-h-screen bg-gray-50">
      <Header
        title="Conversations"
        subtitle="View and manage conversation history"
      />
      <div className="p-6">
        <div className="rounded-lg border bg-white p-6 shadow-sm">
          <p className="text-gray-600">Conversations page - Coming soon</p>
        </div>
      </div>
    </div>
  );
};

export default ConversationsPage;
