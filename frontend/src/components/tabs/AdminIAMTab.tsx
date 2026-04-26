/**
 * Admin / IAM Dashboard Tab.
 *
 * Displays users, roles, API keys, session policy, and IP allowlist management.
 */
import { useState, useEffect } from 'react';

interface User {
  id: string;
  email: string;
  role: 'admin' | 'trader' | 'viewer';
  active: boolean;
  lastLogin: string;
}

interface ApiKey {
  id: string;
  name: string;
  created: string;
  lastUsed: string;
  active: boolean;
}

interface IpRule {
  ip: string;
  description: string;
  active: boolean;
}

export default function AdminIAMTab() {
  const [users, setUsers] = useState<User[]>([]);
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [ipRules, setIpRules] = useState<IpRule[]>([]);
  const [activeTab, setActiveTab] = useState<'users' | 'apikeys' | 'ip Rules'>('users');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [usersRes, keysRes, ipRes] = await Promise.all([
        fetch('/api/admin/users'),
        fetch('/api/admin/api-keys'),
        fetch('/api/admin/ip-rules')
      ]);
      if (usersRes.ok) {
        const data = await usersRes.json();
        setUsers(data.users || []);
      }
      if (keysRes.ok) {
        const data = await keysRes.json();
        setApiKeys(data.keys || []);
      }
      if (ipRes.ok) {
        const data = await ipRes.json();
        setIpRules(data.rules || []);
      }
    } catch (err) {
      console.error('Failed to fetch admin data:', err);
    } finally {
      setLoading(false);
    }
  };

  const toggleUser = async (id: string, active: boolean) => {
    try {
      await fetch(`/api/admin/users/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active })
      });
      setUsers(users.map(u => u.id === id ? { ...u, active } : u));
    } catch (err) {
      console.error('Failed to toggle user:', err);
    }
  };

  const deleteApiKey = async (id: string) => {
    if (!confirm('Delete this API key? This cannot be undone.')) return;
    try {
      await fetch(`/api/admin/api-keys/${id}`, { method: 'DELETE' });
      setApiKeys(apiKeys.filter(k => k.id !== id));
    } catch (err) {
      console.error('Failed to delete API key:', err);
    }
  };

  const addIpRule = async (ip: string, description: string) => {
    try {
      const res = await fetch('/api/admin/ip-rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ip, description })
      });
      if (res.ok) {
        const newRule = await res.json();
        setIpRules([...ipRules, newRule]);
      }
    } catch (err) {
      console.error('Failed to add IP rule:', err);
    }
  };

  return (
    <div className="p-4">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold">Admin / IAM Dashboard</h2>
        <button
          onClick={fetchData}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          disabled={loading}
        >
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {/* Tab Navigation */}
      <div className="flex border-b mb-4">
        <button
          className={`px-4 py-2 ${activeTab === 'users' ? 'border-b-2 border-blue-600 font-semibold' : 'text-gray-500'}`}
          onClick={() => setActiveTab('users')}
        >
          Users ({users.length})
        </button>
        <button
          className={`px-4 py-2 ${activeTab === 'apikeys' ? 'border-b-2 border-blue-600 font-semibold' : 'text-gray-500'}`}
          onClick={() => setActiveTab('apikeys')}
        >
          API Keys ({apiKeys.length})
        </button>
        <button
          className={`px-4 py-2 ${activeTab === 'ip Rules' ? 'border-b-2 border-blue-600 font-semibold' : 'text-gray-500'}`}
          onClick={() => setActiveTab('ip Rules')}
        >
          IP Allowlist ({ipRules.length})
        </button>
      </div>

      {/* Users Table */}
      {activeTab === 'users' && (
        <table className="min-w-full bg-white border">
          <thead>
            <tr className="bg-gray-100">
              <th className="px-4 py-2 border">Email</th>
              <th className="px-4 py-2 border">Role</th>
              <th className="px-4 py-2 border">Status</th>
              <th className="px-4 py-2 border">Last Login</th>
              <th className="px-4 py-2 border">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map(user => (
              <tr key={user.id}>
                <td className="px-4 py-2 border">{user.email}</td>
                <td className="px-4 py-2 border">
                  <span className={`px-2 py-1 rounded text-xs ${
                    user.role === 'admin' ? 'bg-purple-100 text-purple-700' :
                    user.role === 'trader' ? 'bg-blue-100 text-blue-700' :
                    'bg-gray-100 text-gray-700'
                  }`}>
                    {user.role}
                  </span>
                </td>
                <td className="px-4 py-2 border">
                  <span className={user.active ? 'text-green-600' : 'text-red-600'}>
                    {user.active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td className="px-4 py-2 border">{user.lastLogin ? new Date(user.lastLogin).toLocaleString() : 'Never'}</td>
                <td className="px-4 py-2 border">
                  <button
                    onClick={() => toggleUser(user.id, !user.active)}
                    className="text-blue-600 hover:underline"
                  >
                    {user.active ? 'Deactivate' : 'Activate'}
                  </button>
                </td>
              </tr>
            ))}
            {users.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-2 text-center text-gray-500">No users found</td>
              </tr>
            )}
          </tbody>
        </table>
      )}

      {/* API Keys Table */}
      {activeTab === 'apikeys' && (
        <table className="min-w-full bg-white border">
          <thead>
            <tr className="bg-gray-100">
              <th className="px-4 py-2 border">Name</th>
              <th className="px-4 py-2 border">Created</th>
              <th className="px-4 py-2 border">Last Used</th>
              <th className="px-4 py-2 border">Status</th>
              <th className="px-4 py-2 border">Actions</th>
            </tr>
          </thead>
          <tbody>
            {apiKeys.map(key => (
              <tr key={key.id}>
                <td className="px-4 py-2 border">{key.name}</td>
                <td className="px-4 py-2 border">{new Date(key.created).toLocaleDateString()}</td>
                <td className="px-4 py-2 border">{key.lastUsed ? new Date(key.lastUsed).toLocaleString() : 'Never'}</td>
                <td className="px-4 py-2 border">
                  <span className={key.active ? 'text-green-600' : 'text-red-600'}>
                    {key.active ? 'Active' : 'Revoked'}
                  </span>
                </td>
                <td className="px-4 py-2 border">
                  {key.active && (
                    <button
                      onClick={() => deleteApiKey(key.id)}
                      className="text-red-600 hover:underline"
                    >
                      Revoke
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {apiKeys.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-2 text-center text-gray-500">No API keys</td>
              </tr>
            )}
          </tbody>
        </table>
      )}

      {/* IP Allowlist */}
      {activeTab === 'ip Rules' && (
        <div>
          <div className="mb-4 p-4 bg-yellow-50 border border-yellow-200 rounded">
            <p className="text-sm text-yellow-700">
              <strong>Note:</strong> IP restrictions apply to API access. Leave empty to allow all IPs.
            </p>
          </div>
          <table className="min-w-full bg-white border">
            <thead>
              <tr className="bg-gray-100">
                <th className="px-4 py-2 border">IP Address</th>
                <th className="px-4 py-2 border">Description</th>
                <th className="px-4 py-2 border">Status</th>
              </tr>
            </thead>
            <tbody>
              {ipRules.map((rule, idx) => (
                <tr key={idx}>
                  <td className="px-4 py-2 border font-mono">{rule.ip}</td>
                  <td className="px-4 py-2 border">{rule.description}</td>
                  <td className="px-4 py-2 border">
                    <span className={rule.active ? 'text-green-600' : 'text-red-600'}>
                      {rule.active ? 'Active' : 'Disabled'}
                    </span>
                  </td>
                </tr>
              ))}
              {ipRules.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-4 py-2 text-center text-gray-500">No IP rules configured</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}