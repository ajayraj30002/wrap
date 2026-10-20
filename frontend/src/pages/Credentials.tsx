import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardHeader } from '../components/ui/Card';
import { Table, TableContainer, TableHead, TableRow, TableHeader, TableBody, TableCell, EmptyState } from '../components/ui/Table';
import { StatusBadge } from '../components/ui/StatusBadge';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { Input, FormGroup, Label, Select } from '../components/ui/Form';
import { LoadingSkeleton } from '../components/ui/LoadingSkeleton';
import { apiClient } from '../lib/apiClient';
import { useToast } from '../contexts/ToastContext';
import { Trash2, Play, Plus, Shield, RefreshCw } from 'lucide-react';

interface Credential {
  id: string;
  provider_id: string;
  provider: string;
  name: string;
  masked_identifier: string;
  enabled: boolean;
  metadata: Record<string, any>;
  last_health_status: string | null;
  last_health_check_at: string | null;
  created_at: string;
  updated_at: string;
}

interface Provider {
  id: string;
  name: string;
  display_name: string;
  enabled: boolean;
  metadata: { default_models?: string[] };
}

export function Credentials() {
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(true);
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const { toast } = useToast();

  // Add credential form state
  const [formProvider, setFormProvider] = useState('');
  const [formName, setFormName] = useState('');
  const [formApiKey, setFormApiKey] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const fetchCreds = useCallback(async () => {
    try {
      const data = await apiClient.get('/api/credentials');
      setCredentials(data);
    } catch (e) {
      toast({ title: 'Failed to load credentials', type: 'error' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  const fetchProviders = useCallback(async () => {
    try {
      const data = await apiClient.get('/api/providers');
      setProviders(data);
    } catch (e) {
      // silent
    }
  }, []);

  useEffect(() => {
    fetchCreds();
    fetchProviders();
  }, [fetchCreds, fetchProviders]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await apiClient.post('/api/credentials', {
        provider: formProvider,
        name: formName,
        api_key: formApiKey,
        metadata: {},
      });
      toast({ title: 'Credential added', description: 'Catalog synced and a default worker was created when a model was available.', type: 'success' });
      setIsAddOpen(false);
      setFormProvider('');
      setFormName('');
      setFormApiKey('');
    } catch (e: any) {
      toast({ title: 'Failed to add credential', description: e.data?.detail || 'Check your inputs.', type: 'error' });
    } finally {
      setIsSubmitting(false);
      fetchCreds();
    }
  };

  const handleTest = async (id: string) => {
    setTestingId(id);
    try {
      const result = await apiClient.post(`/api/credentials/${id}/test`, {});
      if (result.status === 'healthy') {
        toast({ title: 'Credential healthy', description: 'Provider connection verified.', type: 'success' });
      } else {
        toast({ title: 'Credential unhealthy', description: result.error_type || 'Test failed.', type: 'warning' });
      }
      fetchCreds();
    } catch (e: any) {
      toast({ title: 'Test failed', description: e.data?.detail || 'Error', type: 'error' });
      fetchCreds();
    } finally {
      setTestingId(null);
    }
  };

  const handleToggle = async (id: string, current: boolean) => {
    try {
      await apiClient.patch(`/api/credentials/${id}`, { enabled: !current });
      toast({ title: `Credential ${current ? 'disabled' : 'enabled'}`, type: 'success' });
      fetchCreds();
    } catch (e) {
      toast({ title: 'Failed to update credential', type: 'error' });
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm('Delete this credential? All associated workers will be permanently removed.')) return;
    try {
      await apiClient.delete(`/api/credentials/${id}`);
      fetchCreds();
      toast({ title: 'Credential deleted', type: 'success' });
    } catch (e) {
      toast({ title: 'Failed to delete', type: 'error' });
    }
  };

  const handleCatalogSync = async (id: string) => {
    setSyncingId(id);
    try {
      await apiClient.post(`/api/credentials/${id}/catalog/sync`, {});
      toast({ title: 'Catalog refreshed', type: 'success' });
      fetchCreds();
    } catch (e: any) {
      toast({ title: 'Catalog refresh failed', description: e.data?.detail || 'Provider catalog unavailable.', type: 'warning' });
    } finally {
      setSyncingId(null);
    }
  };

  return (
    <div className="page-container">
      <div className="page-header flex justify-between items-center">
        <div>
          <h1>Credentials</h1>
          <p className="page-subtitle">Manage provider API keys. Workers are created separately from the provider model catalog.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn btn-secondary btn-sm flex items-center gap-1"
            onClick={fetchCreds}
            disabled={loading}
            title="Refresh credentials"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            <span>{loading ? "Refreshing..." : "Refresh"}</span>
          </button>
          <Button onClick={() => setIsAddOpen(true)} icon={<Plus size={16} />}>Add Credential</Button>
        </div>
      </div>

      <Card>
        <CardHeader title="Provider Credentials" description={`${credentials.length} credential${credentials.length !== 1 ? 's' : ''} configured`} />
        <TableContainer>
          {loading ? (
            <LoadingSkeleton rows={3} cols={5} />
          ) : credentials.length === 0 ? (
            <EmptyState
              icon={<Shield size={36} />}
              title="No provider credentials configured"
              description="Add a provider API key (Groq, Cerebras, Gemini) to start routing requests through WRAP."
              action={<Button onClick={() => setIsAddOpen(true)} icon={<Plus size={16} />}>Add Credential</Button>}
            />
          ) : (
            <Table>
              <TableHead>
                <TableRow>
                  <TableHeader>Provider</TableHeader>
                  <TableHeader>Name</TableHeader>
                  <TableHeader>Key</TableHeader>
                  <TableHeader>Health</TableHeader>
                  <TableHeader>Enabled</TableHeader>
                  <TableHeader>Actions</TableHeader>
                </TableRow>
              </TableHead>
              <TableBody>
                {credentials.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell><span className="font-medium text-primary">{c.provider}</span></TableCell>
                    <TableCell>{c.name}</TableCell>
                    <TableCell><code>{c.masked_identifier}</code></TableCell>
                    <TableCell><StatusBadge status={c.last_health_status || 'unknown'} /></TableCell>
                    <TableCell>
                      <label className="toggle">
                        <input type="checkbox" checked={c.enabled} onChange={() => handleToggle(c.id, c.enabled)} />
                        <span className="toggle-slider" />
                      </label>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <button
                          className="btn btn-ghost"
                          title="Test Connection"
                          onClick={() => handleTest(c.id)}
                          disabled={testingId === c.id}
                        >
                          <Play size={14} />
                        </button>
                        <button
                          className="btn btn-ghost"
                          title="Refresh Catalog"
                          onClick={() => handleCatalogSync(c.id)}
                          disabled={syncingId === c.id}
                        >
                          <RefreshCw size={14} className={syncingId === c.id ? "animate-spin" : ""} />
                        </button>
                        <button className="btn btn-ghost text-error" title="Delete" onClick={() => handleDelete(c.id)}>
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </TableContainer>
      </Card>

      {/* Add Credential Modal */}
      <Modal isOpen={isAddOpen} onClose={() => setIsAddOpen(false)} title="Add Provider Credential">
        <form onSubmit={handleAdd}>
          <FormGroup>
            <Label>Provider</Label>
              <Select value={formProvider} onChange={e => setFormProvider(e.target.value)} required>
              <option value="">Select a provider…</option>
              {providers.map(p => (
                <option key={p.name} value={p.name}>{p.display_name}</option>
              ))}
            </Select>
          </FormGroup>

          <FormGroup>
            <Label>Credential Name</Label>
            <Input
              placeholder="e.g. groq-primary"
              value={formName}
              onChange={e => setFormName(e.target.value)}
              required
              maxLength={120}
            />
            <div className="form-hint">A label to identify this credential.</div>
          </FormGroup>

          <FormGroup>
            <Label>API Key / Secret</Label>
            <Input
              type="password"
              placeholder="Paste your provider API key"
              value={formApiKey}
              onChange={e => setFormApiKey(e.target.value)}
              required
              autoComplete="off"
            />
            <div className="form-hint">Encrypted at rest. Only a masked version will be visible after saving.</div>
          </FormGroup>

          <div className="flex justify-end gap-2 mt-4">
            <Button type="button" variant="ghost" onClick={() => setIsAddOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={isSubmitting || !formProvider || !formName || !formApiKey}>
              {isSubmitting ? 'Adding…' : 'Add Credential'}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
