import { useState, useEffect } from 'react';
import Card from '../components/Card';
import Button from '../components/Button';
import { getTables, getTableSchema, getDatabaseStats } from '../services/api.service';

interface TableInfo {
  table_name: string;
  column_count: number;
}

interface ColumnInfo {
  column_name: string;
  data_type: string;
  max_length: number | null;
  nullable: boolean;
  default: string | null;
}

interface TableSchema {
  table_name: string;
  columns: ColumnInfo[];
  total_columns: number;
}

interface DatabaseStats {
  total_tables: number;
  total_rows: number;
  table_stats: Array<{
    table_name: string;
    row_count: number;
  }>;
}

export default function DatabasePage() {
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [selectedTable, setSelectedTable] = useState<string>('');
  const [tableSchema, setTableSchema] = useState<TableSchema | null>(null);
  const [stats, setStats] = useState<DatabaseStats | null>(null);
  const [activeTab, setActiveTab] = useState<'schema' | 'stats'>('stats');

  // Load stats on mount
  useEffect(() => {
    handleGetStats();
  }, []);

  const handleGetTables = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await getTables();
      setTables(response.tables || []);
    } catch (err: any) {
      setError(err.message || 'Failed to get tables');
    } finally {
      setLoading(false);
    }
  };

  const handleGetTableSchema = async (tableName: string) => {
    setLoading(true);
    setError(null);
    setTableSchema(null);

    try {
      const response = await getTableSchema(tableName);
      setTableSchema(response);
      setSelectedTable(tableName);
    } catch (err: any) {
      setError(err.message || 'Failed to get table schema');
    } finally {
      setLoading(false);
    }
  };

  const handleGetStats = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await getDatabaseStats();
      setStats(response);
    } catch (err: any) {
      setError(err.message || 'Failed to get database stats');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Database Explorer</h1>
        <p className="mt-1 text-sm text-gray-500">
          View database statistics and explore table schemas
        </p>
      </div>

      {/* Error Display */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-md p-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">Error</h3>
              <p className="mt-1 text-sm text-red-700">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => {
              setActiveTab('stats');
              handleGetStats();
            }}
            className={`${
              activeTab === 'stats'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm`}
          >
            📊 Statistics
          </button>
          <button
            onClick={() => {
              setActiveTab('schema');
              if (tables.length === 0) handleGetTables();
            }}
            className={`${
              activeTab === 'schema'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm`}
          >
            🗄️ Schema Explorer
          </button>
        </nav>
      </div>

      {/* Statistics Tab */}
      {activeTab === 'stats' && (
        <div className="space-y-6">
          {loading && !stats ? (
            <div className="text-center py-12">
              <p className="text-gray-500">Loading statistics...</p>
            </div>
          ) : stats ? (
            <>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <Card>
                  <div className="text-center">
                    <p className="text-sm font-medium text-gray-500">Total Tables</p>
                    <p className="text-3xl font-bold text-blue-600 mt-2">{stats.total_tables}</p>
                  </div>
                </Card>
                <Card>
                  <div className="text-center">
                    <p className="text-sm font-medium text-gray-500">Total Rows</p>
                    <p className="text-3xl font-bold text-green-600 mt-2">
                      {stats.total_rows.toLocaleString()}
                    </p>
                  </div>
                </Card>
                <Card>
                  <div className="text-center">
                    <p className="text-sm font-medium text-gray-500">Average Rows/Table</p>
                    <p className="text-3xl font-bold text-purple-600 mt-2">
                      {stats.total_tables > 0 ? Math.round(stats.total_rows / stats.total_tables) : 0}
                    </p>
                  </div>
                </Card>
              </div>

              <Card>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-medium text-gray-900">Table Statistics</h3>
                  <Button variant="secondary" size="sm" onClick={handleGetStats} disabled={loading}>
                    {loading ? 'Loading...' : '🔄 Refresh'}
                  </Button>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Table Name
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Row Count
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Distribution
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {stats.table_stats.map((table) => (
                        <tr key={table.table_name} className="hover:bg-gray-50">
                          <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                            📋 {table.table_name}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                            {table.row_count.toLocaleString()}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                            <div className="flex items-center">
                              <div className="w-32 bg-gray-200 rounded-full h-2 mr-2">
                                <div
                                  className="bg-blue-600 h-2 rounded-full"
                                  style={{
                                    width: `${stats.total_rows > 0 ? (table.row_count / stats.total_rows) * 100 : 0}%`
                                  }}
                                />
                              </div>
                              <span>
                                {stats.total_rows > 0 
                                  ? ((table.row_count / stats.total_rows) * 100).toFixed(1)
                                  : 0}%
                              </span>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </>
          ) : (
            <div className="text-center py-12">
              <p className="text-gray-500">No statistics available</p>
            </div>
          )}
        </div>
      )}

      {/* Schema Explorer Tab */}
      {activeTab === 'schema' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card className="lg:col-span-1">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-medium text-gray-900">Tables</h3>
                <Button variant="secondary" size="sm" onClick={handleGetTables} disabled={loading}>
                  Refresh
                </Button>
              </div>
              {loading && tables.length === 0 ? (
                <div className="text-center py-8">
                  <p className="text-gray-500">Loading tables...</p>
                </div>
              ) : tables.length > 0 ? (
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {tables.map((table) => (
                    <button
                      key={table.table_name}
                      onClick={() => handleGetTableSchema(table.table_name)}
                      className={`w-full text-left px-3 py-2 rounded-md text-sm ${
                        selectedTable === table.table_name
                          ? 'bg-blue-50 text-blue-700 font-medium'
                          : 'hover:bg-gray-50 text-gray-700'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span>📋 {table.table_name}</span>
                        <span className="text-xs text-gray-500">{table.column_count} cols</span>
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8">
                  <p className="text-gray-500">No tables found</p>
                </div>
              )}
            </div>
          </Card>

          <Card className="lg:col-span-2">
            {loading && selectedTable ? (
              <div className="text-center py-12">
                <p className="text-gray-500">Loading schema...</p>
              </div>
            ) : tableSchema ? (
              <div className="space-y-4">
                <h3 className="text-lg font-medium text-gray-900">
                  📋 {tableSchema.table_name} <span className="text-sm font-normal text-gray-500">({tableSchema.total_columns} columns)</span>
                </h3>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Column
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Type
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Nullable
                        </th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                          Default
                        </th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {tableSchema.columns.map((col) => (
                        <tr key={col.column_name} className="hover:bg-gray-50">
                          <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                            {col.column_name}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                            <code className="bg-gray-100 px-2 py-1 rounded text-xs">
                              {col.data_type}
                              {col.max_length && `(${col.max_length})`}
                            </code>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm">
                            {col.nullable ? (
                              <span className="text-green-600">✓ Yes</span>
                            ) : (
                              <span className="text-red-600">✗ No</span>
                            )}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                            {col.default ? (
                              <code className="bg-gray-100 px-2 py-1 rounded text-xs">{col.default}</code>
                            ) : (
                              <span className="text-gray-400">-</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="text-center py-12">
                <p className="text-gray-500">👈 Select a table to view its schema</p>
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
