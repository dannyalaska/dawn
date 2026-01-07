'use client';

import { BoltIcon, CubeIcon, ServerStackIcon, SparklesIcon } from '@heroicons/react/24/outline';
import useDawnData from '@/hooks/useDawnData';
import { fetchHealth } from '@/lib/api';
import type { ServiceHealth } from '@/lib/types';

const indicators = [
  {
    key: 'api',
    label: 'FastAPI Core',
    icon: ServerStackIcon,
    resolve: (health: ServiceHealth | undefined) => Boolean(health?.ok)
  },
  {
    key: 'redis',
    label: 'Redis memory',
    icon: BoltIcon,
    resolve: (health: ServiceHealth | undefined) => Boolean(health?.redis)
  },
  {
    key: 'db',
    label: 'Postgres metrics',
    icon: CubeIcon,
    resolve: (health: ServiceHealth | undefined) => Boolean(health?.db)
  },
  {
    key: 'llm',
    label: 'LLM tooling',
    icon: SparklesIcon,
    resolve: (health: ServiceHealth | undefined) => Boolean(health?.llm?.ok)
  }
];

const pulseColors = {
  true: 'bg-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.8)]',
  false: 'bg-rose-400 shadow-[0_0_12px_rgba(244,63,94,0.8)]'
};

export default function ServiceStatusPanel() {
  const { data, error, isLoading } = useDawnData(['service-health'], ({ token, apiBase }) =>
    fetchHealth({ token, apiBase })
  );

  const llmDetail = data?.llm?.detail || data?.llm?.provider;

  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
      <p className="text-xs uppercase tracking-[0.35em] text-slate-400">Systems check</p>
      <h3 className="mt-1 text-xl font-semibold text-white">Cluster vitals</h3>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {indicators.map(({ key, label, icon: Icon, resolve }) => {
          const ok = resolve(data);
          const statusLabel = isLoading ? 'Checking…' : ok ? 'Online' : 'Offline';
          return (
            <div key={key} className="flex items-center gap-3 rounded-2xl border border-white/10 px-3 py-2">
              <span className={`h-2 w-2 rounded-full ${pulseColors[ok ? 'true' : 'false']}`} />
              <Icon className="h-5 w-5 text-slate-200" />
              <div className="min-w-0">
                <p className="text-sm font-medium text-white">{label}</p>
                <p className="truncate text-xs text-slate-400">{statusLabel}</p>
              </div>
            </div>
          );
        })}
      </div>
      {llmDetail && <p className="mt-3 text-xs text-slate-400">LLM provider — {llmDetail}</p>}
      {error && <p className="mt-2 text-xs text-rose-400">Health check failed: {error.message}</p>}
    </div>
  );
}
