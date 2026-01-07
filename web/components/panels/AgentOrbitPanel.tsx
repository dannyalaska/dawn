'use client';

import DataAurora from '@/components/charts/DataAurora';
import type { AgentRunSummary } from '@/lib/types';

interface AgentOrbitPanelProps {
  result: AgentRunSummary | null;
}

export default function AgentOrbitPanel({ result }: AgentOrbitPanelProps) {
  return (
    <div className="glass-panel rounded-3xl border border-white/5 p-6">
      <p className="text-sm uppercase tracking-[0.4em] text-slate-400">Agents</p>
      <h3 className="mt-2 text-2xl font-semibold text-white">Swarm telemetry</h3>
      <p className="mt-2 text-sm text-slate-300">
        Visualize context embeddings as glowing particles while the orchestration graph spins up plans.
      </p>
      <div className="mt-4">
        <DataAurora />
      </div>
      {result && (
        <div className="mt-4 rounded-2xl border border-white/10 bg-black/30 p-4 text-sm text-slate-100">
          <p className="font-semibold">{result.feed_identifier}</p>
          <p className="mt-1 text-slate-300">{result.answer || 'No direct answer yet.'}</p>
          {result.warnings?.length ? (
            <ul className="mt-2 text-xs text-amber-200">
              {result.warnings.map((warning, idx) => (
                <li key={idx}>⚠️ {warning}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-xs text-emerald-200">Swarm ready with {result.completed?.length ?? 0} steps.</p>
          )}
        </div>
      )}
    </div>
  );
}
