'use client';

import { useState } from 'react';
import { useDawnSession } from '@/context/dawn-session';
import useDawnData from '@/hooks/useDawnData';
import { dawnRequest } from '@/lib/api';
import clsx from 'clsx';

interface ProviderStatus {
  provider: string;
  model: string;
  has_api_key: { anthropic: boolean; openai: boolean };
}

const PROVIDERS = [
  {
    id: 'lmstudio',
    label: 'LM Studio',
    icon: '💻',
    description: 'Local-first. Requires LM Studio server.',
    defaultModel: 'mistral-7b-instruct-v0.3',
    defaultBase: 'http://127.0.0.1:1234',
    fields: ['model', 'base_url'] as const,
  },
  {
    id: 'ollama',
    label: 'Ollama',
    icon: '🦙',
    description: 'Local models via Ollama.',
    defaultModel: 'llama3.1',
    defaultBase: 'http://127.0.0.1:11434',
    fields: ['model', 'base_url'] as const,
  },
  {
    id: 'openai',
    label: 'OpenAI',
    icon: '🤖',
    description: 'GPT-4o and friends.',
    defaultModel: 'gpt-4o-mini',
    defaultBase: '',
    fields: ['model', 'api_key'] as const,
  },
  {
    id: 'anthropic',
    label: 'Claude',
    icon: '✦',
    description: 'Claude Sonnet · cloud API.',
    defaultModel: 'claude-sonnet-4-6',
    defaultBase: '',
    fields: ['model', 'api_key'] as const,
  },
] as const;

type ProviderId = (typeof PROVIDERS)[number]['id'];

function fetchProviderStatus({ token, apiBase }: { token: string | null; apiBase: string }) {
  return dawnRequest<ProviderStatus>('/lmstudio/provider', { token, apiBase });
}

async function activateProvider(
  provider: ProviderId,
  model: string,
  extras: { base_url?: string; api_key?: string },
  opts: { token: string | null; apiBase: string },
) {
  return dawnRequest('/lmstudio/use', {
    method: 'POST',
    json: { provider, model, ...extras },
    ...opts,
  });
}

export default function ModelProviderPanel() {
  const { token, apiBase } = useDawnSession();
  const { data, mutate } = useDawnData(['provider-status'], fetchProviderStatus);

  const [expanded, setExpanded] = useState<ProviderId | null>(null);
  const [formState, setFormState] = useState<Record<ProviderId, { model: string; base_url: string; api_key: string }>>({
    lmstudio: { model: 'mistral-7b-instruct-v0.3', base_url: 'http://127.0.0.1:1234', api_key: '' },
    ollama: { model: 'llama3.1', base_url: 'http://127.0.0.1:11434', api_key: '' },
    openai: { model: 'gpt-4o-mini', base_url: '', api_key: '' },
    anthropic: { model: 'claude-sonnet-4-6', base_url: '', api_key: '' },
  });
  const [saving, setSaving] = useState<ProviderId | null>(null);
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null);

  const activeProvider = data?.provider ?? 'stub';

  const setField = (pid: ProviderId, field: string, value: string) => {
    setFormState(prev => ({ ...prev, [pid]: { ...prev[pid], [field]: value } }));
  };

  const handleActivate = async (pid: ProviderId) => {
    setSaving(pid);
    setMessage(null);
    const f = formState[pid];
    const extras: { base_url?: string; api_key?: string } = {};
    if (f.base_url) extras.base_url = f.base_url;
    if (f.api_key) extras.api_key = f.api_key;
    try {
      await activateProvider(pid, f.model, extras, { token, apiBase });
      setMessage({ text: `${pid} set as active provider. Restart backend to apply.`, ok: true });
      mutate();
    } catch (err) {
      setMessage({ text: err instanceof Error ? err.message : 'Failed to switch provider.', ok: false });
    } finally {
      setSaving(null);
    }
  };

  return (
    <div className="space-y-2">
      {PROVIDERS.map(p => {
        const isActive = activeProvider === p.id;
        const isOpen = expanded === p.id;
        const needsKey =
          (p.id === 'anthropic' && !data?.has_api_key?.anthropic) ||
          (p.id === 'openai' && !data?.has_api_key?.openai);

        return (
          <div
            key={p.id}
            className={clsx(
              'rounded-2xl border transition-all',
              isActive
                ? 'border-cyan-400/40 bg-cyan-400/5'
                : 'border-white/8 bg-white/3 hover:bg-white/5',
            )}
          >
            {/* tile header */}
            <button
              type="button"
              className="flex w-full items-center gap-3 px-3 py-2.5 text-left"
              onClick={() => setExpanded(isOpen ? null : p.id)}
            >
              <span className="text-base leading-none">{p.icon}</span>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold text-slate-200">{p.label}</p>
                <p className="truncate text-[10px] text-slate-500">{p.description}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {isActive && (
                  <span className="rounded-full bg-cyan-400/15 px-2 py-0.5 text-[10px] font-semibold text-cyan-300">
                    ACTIVE
                  </span>
                )}
                {needsKey && !isActive && (
                  <span className="rounded-full bg-amber-400/15 px-2 py-0.5 text-[10px] font-semibold text-amber-300">
                    NEEDS KEY
                  </span>
                )}
              </div>
            </button>

            {/* expanded config */}
            {isOpen && (
              <div className="border-t border-white/8 px-3 pb-3 pt-2 space-y-2">
                {/* model */}
                <label className="block text-[10px] uppercase tracking-[0.25em] text-slate-500">
                  Model
                </label>
                <input
                  className="w-full rounded-xl border border-white/8 bg-black/40 px-3 py-1.5 text-xs text-slate-200 outline-none focus:border-cyan-400/40"
                  value={formState[p.id].model}
                  onChange={e => setField(p.id, 'model', e.target.value)}
                  placeholder={p.defaultModel}
                />
                {/* base_url for local providers */}
                {(p.id === 'lmstudio' || p.id === 'ollama') && (
                  <>
                    <label className="block text-[10px] uppercase tracking-[0.25em] text-slate-500">
                      Base URL
                    </label>
                    <input
                      className="w-full rounded-xl border border-white/8 bg-black/40 px-3 py-1.5 text-xs text-slate-200 outline-none focus:border-cyan-400/40"
                      value={formState[p.id].base_url}
                      onChange={e => setField(p.id, 'base_url', e.target.value)}
                      placeholder={p.defaultBase}
                    />
                  </>
                )}
                {/* api_key for cloud providers */}
                {(p.id === 'anthropic' || p.id === 'openai') && (
                  <>
                    <label className="block text-[10px] uppercase tracking-[0.25em] text-slate-500">
                      API Key {data?.has_api_key?.[p.id as 'anthropic' | 'openai'] ? '(saved — leave blank to keep)' : '(required)'}
                    </label>
                    <input
                      type="password"
                      className="w-full rounded-xl border border-white/8 bg-black/40 px-3 py-1.5 text-xs text-slate-200 outline-none focus:border-cyan-400/40"
                      value={formState[p.id].api_key}
                      onChange={e => setField(p.id, 'api_key', e.target.value)}
                      placeholder={data?.has_api_key?.[p.id as 'anthropic' | 'openai'] ? '••••••••' : 'sk-ant-...'}
                    />
                  </>
                )}
                <button
                  type="button"
                  disabled={saving === p.id}
                  onClick={() => handleActivate(p.id)}
                  className="mt-1 w-full rounded-xl bg-gradient-to-r from-cyan-500/80 to-violet-500/80 py-1.5 text-xs font-semibold text-white shadow disabled:opacity-50"
                >
                  {saving === p.id ? 'Saving…' : isActive ? 'Update config' : 'Use this provider'}
                </button>
              </div>
            )}
          </div>
        );
      })}

      {message && (
        <p className={clsx('text-[11px]', message.ok ? 'text-emerald-400' : 'text-rose-400')}>
          {message.text}
        </p>
      )}
    </div>
  );
}
