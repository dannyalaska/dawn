'use client';

import { useEffect, useState } from 'react';
import DataAurora from '@/components/charts/DataAurora';
import type { AgentRunSummary } from '@/lib/types';

interface AgentOrbitPanelProps {
  result: AgentRunSummary | null;
}

export default function AgentOrbitPanel({ result }: AgentOrbitPanelProps) {
  const [demoStreaming, setDemoStreaming] = useState(false);

  useEffect(() => {
    const handleFocus = (event: Event) => {
      const customEvent = event as CustomEvent;
      if (customEvent.detail?.tileId !== 'agentOrbit') return;
      setDemoStreaming(true);
      window.setTimeout(() => setDemoStreaming(false), 2600);
    };
    const handleAgentTrigger = () => {
      setDemoStreaming(true);
      window.setTimeout(() => setDemoStreaming(false), 2600);
    };
    window.addEventListener('demo:focus-tile', handleFocus);
    window.addEventListener('demo:agent-trigger', handleAgentTrigger);
    return () => {
      window.removeEventListener('demo:focus-tile', handleFocus);
      window.removeEventListener('demo:agent-trigger', handleAgentTrigger);
    };
  }, []);

  return (
    <div className="glass-panel rounded-3xl border border-white/5 p-6">
      <p className="text-sm uppercase tracking-[0.4em] text-slate-400">Agents</p>
      <h3 className="mt-2 text-2xl font-semibold text-white">Swarm telemetry</h3>
      <p className="mt-2 text-sm text-slate-300">
        Visualize context embeddings as glowing particles while the orchestration graph spins up plans.
      </p>
      {demoStreaming && (
        <div className="mt-3 inline-flex items-center gap-2 rounded-full border border-sky-300/30 bg-sky-400/10 px-3 py-1 text-xs uppercase tracking-[0.3em] text-sky-200">
          <span className="h-2 w-2 rounded-full bg-sky-300 animate-pulse" />
          Streaming signals
        </div>
      )}
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
