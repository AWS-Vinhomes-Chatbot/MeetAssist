import { useState } from 'react';
import Card from '../components/Card';
import Button from '../components/Button';
import { executeSql, getTables, getTableSchema, getDatabaseStats } from '../services/api.service';

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
  const [sqlQuery, setSqlQuery] = useState('');
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [selectedTable, setSelectedTable] = useState<string>('');
  const [tableSchema, setTableSchema] = useState<TableSchema | null>(null);
  const [stats, setStats] = useState<DatabaseStats | null>(null);
  const [activeTab, setActiveTab] = useState<'execute' | 'schema' | 'stats'>('execute');

  const handleExecuteSQL = async () => {
    if (!sqlQuery.trim()) {
      setError('Please enter a SQL query');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await executeSql(sqlQuery);
      setResult(response);
      console.log('SQL executed successfully:', response);
    } catch (err: any) {
      setError(err.message || 'Failed to execute SQL');
      console.error('SQL execution error:', err);
    } finally {
      setLoading(false);
    }
  };

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

  const sampleQueries = [
    {
      label: 'Select All Courses',
      sql: 'SELECT * FROM Course LIMIT 10;'
    },
    {
      label: 'Count Accounts by Role',
      sql: 'SELECT r.RoleName, COUNT(a.AccountID) as total FROM Account a JOIN Role r ON a.RoleID = r.RoleID GROUP BY r.RoleName;'
    },
    {
      label: 'Insert New Course',
      sql: `INSERT INTO Course (CourseName, Risk, Description, Status, IsDisabled) VALUES ('Khóa học mới', 'cao', 'Mô tả khóa học', 'active', false);`
    },
    {
      label: 'Update Article Status',
      sql: `UPDATE Article SET Status = 'Published' WHERE BlogID = 1;`
    }
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Database Management</h1>
        <p className="mt-1 text-sm text-gray-500">
          Execute SQL queries and manage your database
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('execute')}
            className={`${
              activeTab === 'execute'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm`}
          >
            Execute SQL
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
            Schema Explorer
          </button>
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
            Statistics
          </button>
        </nav>
      </div>

      {/* Execute SQL Tab */}
      {activeTab === 'execute' && (
        <div className="space-y-4">
          <Card>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  SQL Query
                </label>
                <textarea
                  value={sqlQuery}
                  onChange={(e) => setSqlQuery(e.target.value)}
                  rows={10}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
                  placeholder="Enter your SQL query here..."
                />
              </div>

              <div className="flex items-center justify-between">
                <div className="flex gap-2">
                  <Button onClick={handleExecuteSQL} disabled={loading}>
                    {loading ? 'Executing...' : 'Execute SQL'}
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setSqlQuery('');
                      setResult(null);
                      setError(null);
                    }}
                  >
                    Clear
                  </Button>
                </div>
              </div>

              {/* Sample Queries */}
              <div className="border-t pt-4">
                <p className="text-sm font-medium text-gray-700 mb-2">Sample Queries:</p>
                <div className="flex flex-wrap gap-2">
                  {sampleQueries.map((query, index) => (
                    <button
                      key={index}
                      onClick={() => setSqlQuery(query.sql)}
                      className="px-3 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded-md text-gray-700"
                    >
                      {query.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </Card>

          {/* Error Display */}
          {error && (
            <Card>
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
            </Card>
          )}

          {/* Result Display */}
          {result && (
            <Card>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-medium text-gray-900">Query Results</h3>
                  <span className="text-sm text-gray-500">
                    {result.rows_affected !== undefined
                      ? `${result.rows_affected} rows affected`
                      : `${result.rows_returned} rows returned`}
                  </span>
                </div>

                {result.data && result.data.length > 0 && (
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-gray-50">
                        <tr>
                          {Object.keys(result.data[0]).map((key) => (
                            <th
                              key={key}
                              className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                            >
                              {key}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-200">
                        {result.data.map((row: any, idx: number) => (
                          <tr key={idx}>
                            {Object.values(row).map((value: any, cellIdx: number) => (
                              <td key={cellIdx} className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                {value !== null ? String(value) : 'NULL'}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {result.message && (
                  <div className="bg-green-50 border border-green-200 rounded-md p-4">
                    <p className="text-sm text-green-800">{result.message}</p>
                  </div>
                )}
              </div>
            </Card>
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
                <Button variant="secondary" size="sm" onClick={handleGetTables}>
                  Refresh
                </Button>
              </div>
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
                      <span>{table.table_name}</span>
                      <span className="text-xs text-gray-500">{table.column_count} cols</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </Card>

          <Card className="lg:col-span-2">
            {tableSchema ? (
              <div className="space-y-4">
                <h3 className="text-lg font-medium text-gray-900">
                  {tableSchema.table_name} Schema
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
                        <tr key={col.column_name}>
                          <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                            {col.column_name}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                            {col.data_type}
                            {col.max_length && `(${col.max_length})`}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                            {col.nullable ? 'Yes' : 'No'}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                            {col.default || '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="text-center py-12">
                <p className="text-gray-500">Select a table to view its schema</p>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Statistics Tab */}
      {activeTab === 'stats' && stats && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card>
            <div className="text-center">
              <p className="text-sm font-medium text-gray-500">Total Tables</p>
              <p className="text-3xl font-bold text-gray-900 mt-2">{stats.total_tables}</p>
            </div>
          </Card>
          <Card>
            <div className="text-center">
              <p className="text-sm font-medium text-gray-500">Total Rows</p>
              <p className="text-3xl font-bold text-gray-900 mt-2">
                {stats.total_rows.toLocaleString()}
              </p>
            </div>
          </Card>
          <Card>
            <div className="text-center">
              <p className="text-sm font-medium text-gray-500">Average Rows/Table</p>
              <p className="text-3xl font-bold text-gray-900 mt-2">
                {Math.round(stats.total_rows / stats.total_tables)}
              </p>
            </div>
          </Card>

          <Card className="md:col-span-3">
            <h3 className="text-lg font-medium text-gray-900 mb-4">Table Statistics</h3>
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
                      Percentage
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {stats.table_stats.map((table) => (
                    <tr key={table.table_name}>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                        {table.table_name}
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
                                width: `${(table.row_count / stats.total_rows) * 100}%`
                              }}
                            />
                          </div>
                          <span>
                            {((table.row_count / stats.total_rows) * 100).toFixed(1)}%
                          </span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
