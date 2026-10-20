import { useState, useEffect, useCallback } from 'react';
import { Card, CardHeader } from '../components/ui/Card';
import { Table, TableContainer, TableHead, TableRow, TableHeader, TableBody, TableCell, EmptyState } from '../components/ui/Table';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { Input, FormGroup, Label } from '../components/ui/Form';
import { CopyButton } from '../components/ui/CopyButton';
import { LoadingSkeleton } from '../components/ui/LoadingSkeleton';
import { apiClient } from '../lib/apiClient';
import { useToast } from '../contexts/ToastContext';
import { Plus, Key, Trash2, AlertTriangle, Eye, EyeOff, Copy, Check, RotateCcw } from 'lucide-react';

export function ApiAccess() {
  const [keys, setKeys] = useState<any[]>([]);
  const [models, setModels] = useState<any[]>([]);
  const [keysLoading, setKeysLoading] = useState(true);
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<string | null>(null);
  const [revealedKeys, setRevealedKeys] = useState<Record<string, boolean>>({});
  const [copiedKeyId, setCopiedKeyId] = useState<string | null>(null);
  const [rollingKeyId, setRollingKeyId] = useState<string | null>(null);
  const { toast } = useToast();

  const baseUrl = `${window.location.protocol}//${window.location.hostname}:8000/v1`;

  const fetchKeys = useCallback(async () => {
    try {
      const data = await apiClient.get('/api/apikeys');
      setKeys(data || []);
    } catch (e) {
      toast({ title: 'Failed to load API keys', type: 'error' });
    } finally {
      setKeysLoading(false);
    }
  }, [toast]);

  const fetchModels = useCallback(async () => {
    try {
      const data = await apiClient.get('/api/models');
      setModels(data || []);
    } catch (e) {
      // silent — models are supplementary
    }
  }, []);

  useEffect(() => { fetchKeys(); fetchModels(); }, [fetchKeys, fetchModels]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      const data = await apiClient.post('/api/apikeys', { name: newKeyName });
      setNewlyCreatedKey(data.key);
      fetchKeys();
    } catch (e: any) {
      toast({ title: 'Error', description: e.data?.detail || 'Could not create API key', type: 'error' });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRevoke = async (id: string) => {
    if (!window.confirm('Revoke this API key? This cannot be undone.')) return;
    try {
      await apiClient.delete(`/api/apikeys/${id}`);
      toast({ title: 'Key revoked', type: 'success' });
      fetchKeys();
    } catch (e) {
      toast({ title: 'Failed to revoke key', type: 'error' });
    }
  };

  const handleCopyApiKey = async (k: any) => {
    let keyToCopy = k.key || k.full_key;
    if (!keyToCopy) {
      try {
        const res = await apiClient.get(`/api/apikeys/${k.id}/reveal`);
        if (res?.key) {
          keyToCopy = res.key;
          setKeys((prev) =>
            prev.map((item) =>
              item.id === k.id ? { ...item, key: res.key, full_key: res.key, has_full_key: true } : item
            )
          );
        }
      } catch (err: any) {
        console.warn("Could not reveal key:", err);
      }
    }

    if (keyToCopy && !keyToCopy.includes("***") && !keyToCopy.includes("••••")) {
      navigator.clipboard.writeText(keyToCopy);
      setCopiedKeyId(k.id);
      toast({
        title: "Complete Key Copied!",
        description: `Full key ${keyToCopy.slice(0, 14)}... copied (ready for Roo Code, Continue, or Cursor).`,
        type: "success",
      });
      setTimeout(() => setCopiedKeyId(null), 2500);
    } else {
      toast({
        title: "Legacy Hashed Key",
        description: "This key was stored as a one-way hash. Click Roll to generate a full unmasked key.",
        type: "warning",
      });
    }
  };

  const handleToggleReveal = async (k: any) => {
    const isCurrentlyRevealed = Boolean(revealedKeys[k.id]);
    if (isCurrentlyRevealed) {
      setRevealedKeys((prev) => ({ ...prev, [k.id]: false }));
      return;
    }

    if (!k.key && !k.full_key) {
      try {
        const res = await apiClient.get(`/api/apikeys/${k.id}/reveal`);
        if (res?.key) {
          setKeys((prev) =>
            prev.map((item) =>
              item.id === k.id ? { ...item, key: res.key, full_key: res.key, has_full_key: true } : item
            )
          );
        }
      } catch (e: any) {
        toast({
          title: "Cannot Reveal Key",
          description: e?.data?.detail || "This legacy key has no plaintext. Click Roll to generate a fresh full key.",
          type: "warning",
        });
        return;
      }
    }

    setRevealedKeys((prev) => ({ ...prev, [k.id]: true }));
  };

  const handleRollKey = async (k: any) => {
    if (!window.confirm(`Are you sure you want to roll "${k.name}"? A new random key will be generated immediately and the previous key will be invalidated.`)) {
      return;
    }
    setRollingKeyId(k.id);
    try {
      const res = await apiClient.post(`/api/apikeys/${k.id}/roll`);
      if (res?.key) {
        navigator.clipboard.writeText(res.key);
        setCopiedKeyId(k.id);
        toast({
          title: "Key Rolled Successfully!",
          description: `New key ${res.key.slice(0, 14)}... generated and copied to clipboard!`,
          type: "success",
        });
        setRevealedKeys((prev) => ({ ...prev, [k.id]: true }));
        fetchKeys();
      }
    } catch (e: any) {
      toast({
        title: "Roll Failed",
        description: e?.data?.detail || "Could not roll key",
        type: "error",
      });
    } finally {
      setRollingKeyId(null);
    }
  };

  const handleCloseNewKey = () => {
    setNewlyCreatedKey(null);
    setIsAddOpen(false);
    setNewKeyName('');
  };

  const activeKeys = keys.filter(k => k.status === 'active');
  const firstModel = models.find((m: any) => m.enabled)?.model || 'auto';

  const pythonExample = `from openai import OpenAI

client = OpenAI(
    base_url="${baseUrl}",
    api_key="wrap_YOUR_KEY_HERE"
)

response = client.chat.completions.create(
    model="${firstModel}",
    messages=[{"role": "user", "content": "Hello!"}]
)
print(response.choices[0].message.content)`;

  const curlExample = `curl ${baseUrl}/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer wrap_YOUR_KEY_HERE" \\
  -d '{
    "model": "${firstModel}",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'`;

  return (
    <div className="page-container">
      <div className="page-header">
        <h1>API Access</h1>
        <p className="page-subtitle">Connect any OpenAI-compatible client to your WRAP gateway.</p>
      </div>

      <div className="flex gap-4 flex-col">
        {/* Connection Details */}
        <Card>
          <CardHeader title="Connection Details" />
          <div className="card-body">
            <div className="mb-3">
              <div className="text-xs font-medium mb-1 text-secondary">Base URL</div>
              <div className="flex items-center gap-2">
                <code className="flex-1" style={{ display: 'block', padding: '0.4rem 0.6rem', background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
                  {baseUrl}
                </code>
                <CopyButton text={baseUrl} />
              </div>
            </div>
            <div>
              <div className="text-xs font-medium mb-1 text-secondary">Authentication</div>
              <p className="text-sm text-secondary">
                Use a WRAP API key (below) as a Bearer token. This key authenticates against your WRAP instance — it is <strong>not</strong> a provider credential.
              </p>
            </div>
          </div>
        </Card>

        {/* WRAP API Keys */}
        <Card>
          <CardHeader
            title="WRAP API Keys"
            description={`${activeKeys.length} active key${activeKeys.length !== 1 ? 's' : ''}`}
            action={<Button onClick={() => setIsAddOpen(true)} icon={<Plus size={14} />}>Create Key</Button>}
          />
          <TableContainer>
            {keysLoading ? (
              <LoadingSkeleton rows={2} cols={4} />
            ) : keys.length === 0 ? (
              <EmptyState
                icon={<Key size={28} />}
                title="No API keys generated"
                description="Create an API key to start making requests through WRAP."
                action={<Button onClick={() => setIsAddOpen(true)} icon={<Plus size={14} />}>Create API Key</Button>}
              />
            ) : (
              <Table>
                <TableHead>
                  <TableRow>
                    <TableHeader>Name</TableHeader>
                    <TableHeader>Key</TableHeader>
                    <TableHeader>Created</TableHeader>
                    <TableHeader>Last Used</TableHeader>
                    <TableHeader>Status</TableHeader>
                    <TableHeader></TableHeader>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {keys.map((k) => (
                    <TableRow key={k.id}>
                      <TableCell><span className="font-medium text-primary">{k.name}</span></TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          <code className="text-secondary font-mono text-xs select-all">
                            {revealedKeys[k.id] ? (k.key || k.full_key || k.masked_key) : (k.masked_key || `${k.prefix}••••••••`)}
                          </code>
                          <button
                            type="button"
                            className="btn btn-ghost btn-xs p-1 text-tertiary hover:text-primary"
                            onClick={() => handleToggleReveal(k)}
                            title={revealedKeys[k.id] ? "Hide complete key" : "Reveal complete key"}
                          >
                            {revealedKeys[k.id] ? <EyeOff size={12} /> : <Eye size={12} />}
                          </button>
                        </div>
                      </TableCell>
                      <TableCell>{new Date(k.created_at).toLocaleDateString()}</TableCell>
                      <TableCell>{k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : '—'}</TableCell>
                      <TableCell>
                        <Badge variant={k.status === 'active' ? 'success' : 'error'}>
                          {k.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1">
                          <button
                            className="btn btn-ghost btn-sm text-secondary hover:text-primary"
                            onClick={() => handleCopyApiKey(k)}
                            title="Copy Complete Gateway Key"
                          >
                            {copiedKeyId === k.id ? <Check size={14} className="text-success" /> : <Copy size={14} />}
                          </button>
                          {k.status === 'active' && (
                            <button
                              className="btn btn-ghost btn-sm text-secondary hover:text-primary"
                              onClick={() => handleRollKey(k)}
                              disabled={rollingKeyId === k.id}
                              title="Roll / Regenerate Key"
                            >
                              <RotateCcw size={14} className={rollingKeyId === k.id ? "animate-spin" : ""} />
                            </button>
                          )}
                          {k.status === 'active' && (
                            <button className="btn btn-ghost text-error" onClick={() => handleRevoke(k.id)} title="Revoke"><Trash2 size={14} /></button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </TableContainer>
        </Card>

        {/* Integration Examples */}
        <Card>
          <CardHeader title="Integration Examples" description="Uses your actual configured models" />
          <div className="card-body">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="text-xs font-medium mb-2 text-secondary">OpenAI Python SDK</div>
                <pre className="p-3 rounded" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', overflow: 'auto', fontSize: '0.75rem', lineHeight: 1.6 }}>
                  {pythonExample}
                </pre>
              </div>
              <div>
                <div className="text-xs font-medium mb-2 text-secondary">cURL</div>
                <pre className="p-3 rounded" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', overflow: 'auto', fontSize: '0.75rem', lineHeight: 1.6 }}>
                  {curlExample}
                </pre>
              </div>
            </div>
          </div>
        </Card>

        {/* Available Models */}
        <Card>
          <CardHeader title="Available Models" description="Models exposed through /v1/models based on your configured workers" />
          <TableContainer>
            {models.length === 0 ? (
              <EmptyState title="No models available" description="Add provider credentials to expose models." />
            ) : (
              <Table>
                <TableHead>
                  <TableRow>
                    <TableHeader>Model</TableHeader>
                    <TableHeader>Provider</TableHeader>
                    <TableHeader>Credential</TableHeader>
                    <TableHeader>Status</TableHeader>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {models.map((m: any) => (
                    <TableRow key={m.worker_id}>
                      <TableCell><code>{m.model}</code></TableCell>
                      <TableCell><span className="font-medium">{m.provider_display_name || m.provider}</span></TableCell>
                      <TableCell>{m.credential_name}</TableCell>
                      <TableCell>
                        <Badge variant={m.enabled ? (m.health_status === 'healthy' || m.health_status === 'unknown' ? 'success' : 'warning') : 'neutral'}>
                          {m.enabled ? (m.health_status === 'unknown' ? 'ready' : m.health_status) : 'disabled'}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </TableContainer>
        </Card>
      </div>

      {/* Create API Key Modal */}
      <Modal isOpen={isAddOpen} onClose={handleCloseNewKey} title="Create WRAP API Key">
        {!newlyCreatedKey ? (
          <form onSubmit={handleCreate}>
            <FormGroup>
              <Label>Key Name</Label>
              <Input
                placeholder="e.g. Cursor IDE, Development"
                value={newKeyName}
                onChange={e => setNewKeyName(e.target.value)}
                required
                autoFocus
              />
              <div className="form-hint">A label to identify this key. The key itself will be auto-generated.</div>
            </FormGroup>
            <div className="flex justify-end gap-2 mt-4">
              <Button type="button" variant="ghost" onClick={handleCloseNewKey}>Cancel</Button>
              <Button type="submit" disabled={isSubmitting || !newKeyName.trim()}>
                {isSubmitting ? 'Generating…' : 'Generate Key'}
              </Button>
            </div>
          </form>
        ) : (
          <div>
            <div className="alert alert-warning mb-4">
              <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 2 }} />
              <div><strong>Save this key now.</strong> WRAP only stores a hash. You will not be able to view it again.</div>
            </div>
            <div className="flex items-center gap-2 mb-4">
              <Input readOnly value={newlyCreatedKey} className="font-mono" />
              <CopyButton text={newlyCreatedKey} />
            </div>
            <div className="flex justify-end">
              <Button onClick={handleCloseNewKey}>Done</Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
