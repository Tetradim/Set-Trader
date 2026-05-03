"""Admin / IAM Dashboard Tab.

Displays users, roles, API keys, session policy, and IP allowlist management.
"""
import { useState, useEffect } from 'react';
import { apiFetch } from '@/lib/api';
import { Users, Key, Shield, Settings, Plus, Trash2, RefreshCw, Edit } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';

interface User {
  id: string;
  username: string;
  email: string;
  roles: string[];
  is_active: boolean;
  last_login: string;
  broker_access: string[];
}

interface APIKeyData {
  key: string;
  name: string;
  roles: string[];
  broker_access: string[];
  created_at: string;
  is_active: boolean;
}

export function AdminIAMTab() {
  const [users, setUsers] = useState<User[]>([]);
  const [apiKeys, setApiKeys] = useState<APIKeyData[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'users' | 'apikeys' | 'settings'>('users');

  const fetchAdminData = async () => {
    setLoading(true);
    try {
      const [usersRes, keysRes] = await Promise.all([
        apiFetch('/api/auth/users'),
        apiFetch('/api/auth/api-keys')
      ]);
      setUsers(usersRes.users || []);
      setApiKeys(keysRes.api_keys || []);
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

  useEffect(() => {
    fetchAdminData();
  }, []);

  const formatTime = (dateStr: string) => {
    if (!dateStr) return 'Never';
    return new Date(dateStr).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  if (loading && users.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Shield className="h-8 w-8 text-violet-500" />
          <div>
            <h2 className="text-2xl font-bold">Admin / IAM</h2>
            <p className="text-muted-foreground">User management and access control</p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={fetchAdminData}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Tab Navigation */}
      <div className="flex items-center gap-2 border-b">
        <button
          onClick={() => setActiveTab('users')}
          className={`px-4 py-2 font-medium border-b-2 transition-colors ${
            activeTab === 'users'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <Users className="h-4 w-4 inline mr-2" />
          Users
        </button>
        <button
          onClick={() => setActiveTab('apikeys')}
          className={`px-4 py-2 font-medium border-b-2 transition-colors ${
            activeTab === 'apikeys'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <Key className="h-4 w-4 inline mr-2" />
          API Keys
        </button>
        <button
          onClick={() => setActiveTab('settings')}
          className={`px-4 py-2 font-medium border-b-2 transition-colors ${
            activeTab === 'settings'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <Settings className="h-4 w-4 inline mr-2" />
          Settings
        </button>
      </div>

      {/* Users Tab */}
      {activeTab === 'users' && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-lg">Users</CardTitle>
            <Button size="sm">
              <Plus className="h-4 w-4 mr-2" />
              Add User
            </Button>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-4 py-3 text-left text-sm font-medium">Username</th>
                    <th className="px-4 py-3 text-left text-sm font-medium">Email</th>
                    <th className="px-4 py-3 text-left text-sm font-medium">Roles</th>
                    <th className="px-4 py-3 text-left text-sm font-medium">Broker Access</th>
                    <th className="px-4 py-3 text-left text-sm font-medium">Status</th>
                    <th className="px-4 py-3 text-left text-sm font-medium">Last Login</th>
                    <th className="px-4 py-3 text-left text-sm font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
                        No users found
                      </td>
                    </tr>
                  ) : (
                    users.map((user) => (
                      <tr key={user.id} className="border-b hover:bg-muted/30">
                        <td className="px-4 py-3 font-medium">{user.username}</td>
                        <td className="px-4 py-3 text-muted-foreground">{user.email}</td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-1">
                            {user.roles.map((role) => (
                              <Badge key={role} variant="outline">{role}</Badge>
                            ))}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {user.broker_access.join(', ') || '-'}
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant={user.is_active ? 'default' : 'secondary'}>
                            {user.is_active ? 'Active' : 'Inactive'}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 text-sm text-muted-foreground">
                          {formatTime(user.last_login)}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <Button variant="ghost" size="sm">
                              <Edit className="h-4 w-4" />
                            </Button>
                            <Button variant="ghost" size="sm">
                              <Trash2 className="h-4 w-4 text-red-500" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* API Keys Tab */}
      {activeTab === 'apikeys' && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-lg">API Keys</CardTitle>
            <Button size="sm">
              <Plus className="h-4 w-4 mr-2" />
              Create Key
            </Button>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {apiKeys.length === 0 ? (
                <p className="text-muted-foreground text-center py-8">No API keys found</p>
              ) : (
                apiKeys.map((key, idx) => (
                  <div key={idx} className="p-4 border rounded-lg">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <Key className="h-5 w-5 text-muted-foreground" />
                        <span className="font-medium">{key.name}</span>
                        <Badge variant={key.is_active ? 'default' : 'secondary'}>
                          {key.is_active ? 'Active' : 'Revoked'}
                        </Badge>
                      </div>
                      <Button variant="ghost" size="sm">
                        <Trash2 className="h-4 w-4 text-red-500" />
                      </Button>
                    </div>
                    <div className="text-sm font-mono bg-muted p-2 rounded mb-2">
                      {key.key}
                    </div>
                    <div className="flex items-center gap-4 text-sm text-muted-foreground">
                      <span>Created: {formatTime(key.created_at)}</span>
                      <span>Roles: {key.roles.join(', ')}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Settings Tab */}
      {activeTab === 'settings' && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Session Policy</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">Session Timeout</p>
                  <p className="text-sm text-muted-foreground">Automatically expire sessions after inactivity</p>
                </div>
                <select className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm">
                  <option value="60">60 minutes</option>
                  <option value="120">2 hours</option>
                  <option value="480">8 hours</option>
                  <option value="1440">24 hours</option>
                </select>
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">MFA Required</p>
                  <p className="text-sm text-muted-foreground">Require multi-factor authentication</p>
                </div>
                <Button variant="outline" size="sm">Enable</Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">IP Allowlist</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <Input placeholder="e.g. 192.168.1.0/24" className="flex-1" />
                  <Button size="sm">
                    <Plus className="h-4 w-4" />
                  </Button>
                </div>
                <p className="text-sm text-muted-foreground">
                  No IP restrictions configured. All IPs are allowed.
                </p>
              </div>
            </CardContent>
          </Card>
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