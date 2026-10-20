import { apiClient } from "../lib/apiClient";
import React, { useEffect, useState } from "react";
import { Key, Plus, Trash2, Copy, RefreshCw, Eye, EyeOff, Check, RotateCcw } from "lucide-react";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Modal } from "../components/ui/Modal";
import { Input, FormGroup, Label, Select } from "../components/ui/Form";
import { TableContainer, Table, TableHead, TableBody, TableRow, TableHeader, TableCell, EmptyState } from "../components/ui/Table";
import { Badge } from "../components/ui/Badge";
import { useToast } from "../contexts/ToastContext";

export function ApiKeys() {
  const [keys, setKeys] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [workers, setWorkers] = useState<any[]>([]);
  const [mode, setMode] = useState("AUTO");
  const [policy, setPolicy] = useState("balanced");
  const [specificWorkerId, setSpecificWorkerId] = useState("");
  const [newMaxBudget, setNewMaxBudget] = useState("");
  const [newResetPeriod, setNewResetPeriod] = useState("monthly");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [revealedKeys, setRevealedKeys] = useState<Record<string, boolean>>({});
  const [copiedKeyId, setCopiedKeyId] = useState<string | null>(null);
  const [rollingKeyId, setRollingKeyId] = useState<string | null>(null);
  
  // For showing the newly created raw key
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<string | null>(null);

  const { toast } = useToast();

  const fetchKeys = async () => {
    try {
      const data = await apiClient.get("/api/apikeys");
      setKeys(data);
      setWorkers(await apiClient.get("/api/workers"));
    } catch (e) {
      toast({ title: "Error", description: "Failed to load API keys", type: "error" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchKeys();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      const parsedBudget = newMaxBudget.trim() === "" ? null : Number(newMaxBudget);
      const data = await apiClient.post("/api/apikeys", {
        name: newKeyName,
        worker_selection_mode: mode,
        routing_policy: policy,
        specific_worker_id: mode === "SPECIFIC_WORKER" ? specificWorkerId : null,
        allowed_worker_ids: mode === "WORKER_POOL" && specificWorkerId ? [specificWorkerId] : null,
        max_budget_usd: isNaN(parsedBudget as any) ? null : parsedBudget,
        budget_reset_period: newResetPeriod,
      });
      setNewlyCreatedKey(data.key);
      fetchKeys();
    } catch (e: any) {
      toast({ title: "Error", description: e.data?.detail || "Could not create API key", type: "error" });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRevoke = async (id: string) => {
    if (!window.confirm("Are you sure you want to revoke this API key? This action cannot be undone.")) return;
    try {
      await apiClient.delete(`/api/apikeys/${id}`);
      toast({ title: "Revoked", description: "API key permanently revoked", type: "success" });
      fetchKeys();
    } catch (e) {
      toast({ title: "Error", description: "Could not revoke key", type: "error" });
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

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast({ title: "Copied to clipboard", type: "info" });
  };

  const handleCloseNewKey = () => {
    setNewlyCreatedKey(null);
    setIsAddModalOpen(false);
    setNewKeyName("");
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <p className="text-secondary max-w-2xl">
          Use WRAP API keys to connect Cursor, agents, or any OpenAI-compatible SDK to your local gateway. These keys are strictly for authenticating against your WRAP instance.
        </p>
        <div className="flex items-center gap-2">
          <button
            className="btn btn-secondary btn-sm flex items-center gap-1"
            onClick={fetchKeys}
            disabled={loading}
            title="Refresh API keys"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            <span>{loading ? "Refreshing..." : "Refresh"}</span>
          </button>
          <Button onClick={() => setIsAddModalOpen(true)} icon={<Plus size={16} />}>Create API Key</Button>
        </div>
      </div>

      <Card>
        <TableContainer>
          <Table>
            <TableHead>
              <TableRow>
                <TableHeader>Name</TableHeader>
                <TableHeader>Key Prefix</TableHeader>
                <TableHeader>Created</TableHeader>
                <TableHeader>Status</TableHeader>
                <TableHeader>Scope</TableHeader>
                <TableHeader>Policy</TableHeader>
                <TableHeader>Spend & Budget</TableHeader>
                <TableHeader></TableHeader>
              </TableRow>
            </TableHead>
            <TableBody>
              {keys.map((k) => (
                <TableRow key={k.id}>
                  <TableCell className="font-medium">{k.name}</TableCell>
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
                  <TableCell>
                    {k.status === 'active' ? <Badge variant="success">Active</Badge> : <Badge variant="error">{k.status || 'Revoked'}</Badge>}
                  </TableCell>
                  <TableCell>{k.worker_selection_mode}</TableCell>
                  <TableCell>{k.routing_policy}</TableCell>
                  <TableCell>
                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-baseline gap-1">
                        <span className="font-mono text-xs font-semibold text-primary">
                          ${(k.spend_usd || 0).toFixed(2)}
                        </span>
                        <span className="font-mono text-xs text-tertiary">
                          {k.max_budget_usd != null ? `/ $${Number(k.max_budget_usd).toFixed(2)}` : "(Uncapped)"}
                        </span>
                      </div>
                      {(k.value_saved_usd || 0) > 0 && (
                        <span className="font-mono text-xs text-success" title="Value saved via free tier & cache">
                          +${(k.value_saved_usd || 0).toFixed(2)} saved
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={copiedKeyId === k.id ? <Check size={14} className="text-success" /> : <Copy size={14} />}
                        onClick={() => handleCopyApiKey(k)}
                        title="Copy Complete Gateway Key"
                      />
                      {k.status === 'active' && (
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={<RotateCcw size={14} className={rollingKeyId === k.id ? "animate-spin" : ""} />}
                          onClick={() => handleRollKey(k)}
                          disabled={rollingKeyId === k.id}
                          title="Roll / Regenerate Key"
                        />
                      )}
                      {k.status === 'active' && (
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={<Trash2 size={14} className="text-error" />}
                          onClick={() => handleRevoke(k.id)}
                          title="Revoke Key"
                        />
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {keys.length === 0 && !loading && (
                <TableRow>
                  <TableCell colSpan={8}>
                    <EmptyState 
                      icon={<Key size={32} />}
                      title="No API keys generated"
                      description="Create an API key to start making requests to the gateway."
                    />
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>

      <Modal 
        isOpen={isAddModalOpen} 
        onClose={handleCloseNewKey} 
        title="Create API Key"
      >
        {!newlyCreatedKey ? (
          <form onSubmit={handleCreate}>
            <FormGroup>
              <Label>Key Name</Label>
              <Input 
                placeholder="e.g. Cursor IDE" 
                value={newKeyName} 
                onChange={e => setNewKeyName(e.target.value)} 
                required
                autoFocus
              />
            </FormGroup>
            <FormGroup>
              <Label>Worker Selection Scope</Label>
              <Select value={mode} onChange={(e) => setMode(e.target.value)}>
                <option value="AUTO">AUTO</option>
                <option value="SPECIFIC_WORKER">SPECIFIC_WORKER</option>
                <option value="WORKER_POOL">WORKER_POOL</option>
              </Select>
            </FormGroup>
            <FormGroup>
              <Label>Routing Policy</Label>
              <Select value={policy} onChange={(e) => setPolicy(e.target.value)}>
                <option value="balanced">balanced</option>
                <option value="fastest">fastest</option>
                <option value="quality_first">quality_first</option>
                <option value="quota_saver">quota_saver</option>
              </Select>
            </FormGroup>
            {mode !== "AUTO" && (
              <FormGroup>
                <Label>{mode === "SPECIFIC_WORKER" ? "Pinned Worker" : "Allowed Worker"}</Label>
                <Select value={specificWorkerId} onChange={(e) => setSpecificWorkerId(e.target.value)} required>
                  <option value="">Select worker</option>
                  {workers.map((w) => <option key={w.id} value={w.id}>{w.provider} / {w.model} / {w.credential_name}</option>)}
                </Select>
              </FormGroup>
            )}
            <FormGroup>
              <Label>Hard Spend Cap (Optional USD)</Label>
              <Input
                type="number"
                step="0.01"
                min="0"
                placeholder="e.g. 25.00 (leave empty for uncapped)"
                value={newMaxBudget}
                onChange={(e) => setNewMaxBudget(e.target.value)}
                className="font-mono text-sm"
              />
            </FormGroup>
            <FormGroup>
              <Label>Budget Reset Frequency</Label>
              <Select value={newResetPeriod} onChange={(e) => setNewResetPeriod(e.target.value)}>
                <option value="monthly">Monthly Reset</option>
                <option value="weekly">Weekly Reset</option>
                <option value="daily">Daily Reset</option>
                <option value="total">Lifetime (No Reset)</option>
              </Select>
            </FormGroup>
            <div className="flex justify-end gap-2 mt-6">
              <Button type="button" variant="ghost" onClick={handleCloseNewKey}>Cancel</Button>
              <Button type="submit" disabled={isSubmitting}>{isSubmitting ? "Generating..." : "Generate Key"}</Button>
            </div>
          </form>
        ) : (
          <div>
            <div className="p-4 bg-warning-muted border border-warning rounded-md mb-4 text-sm text-warning">
              <strong>Save this key now.</strong> For security reasons, WRAP only stores a hash of your API key. You will not be able to view it again.
            </div>
            <div className="flex items-center gap-2 mb-6">
              <Input readOnly value={newlyCreatedKey} className="font-mono text-primary bg-bg-elevated" />
              <Button type="button" onClick={() => copyToClipboard(newlyCreatedKey)} icon={<Copy size={16} />} />
            </div>
            <div className="flex justify-end">
              <Button onClick={handleCloseNewKey}>Done</Button>
            </div>
          </div>
        )}
      </Modal>

      <div className="mt-8">
        <h3 className="font-medium mb-3">Developer Usage</h3>
        <Card className="p-4 bg-bg-base border-border-subtle">
          <pre className="text-sm font-mono text-secondary overflow-x-auto">
{`curl http://localhost:8000/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer wrap_YOUR_API_KEY" \\
  -d '{
    "model": "llama3-70b-8192",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'`}
          </pre>
        </Card>
      </div>
    </div>
  );
}

