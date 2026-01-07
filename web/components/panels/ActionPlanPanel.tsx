'use client';

import { useEffect, useState } from 'react';
import type { FeedRecord, IndexExcelResponse, AgentRunSummary } from '@/lib/types';
import { runAgents } from '@/lib/api';
import { useDawnSession } from '@/context/dawn-session';

interface ActionPlanPanelProps {
  feed: FeedRecord | null;
  summary: IndexExcelResponse | null;
}

export default function ActionPlanPanel({ feed, summary }: ActionPlanPanelProps) {
  const { token, apiBase } = useDawnSession();
  const [plan, setPlan] = useState<AgentRunSummary | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let ignore = false;
    async function runPlan() {
      if (!feed || !summary) return;
      setPending(true);
      setError('');
      try {
        const res = await runAgents(
          {
            feed_identifier: feed.identifier,
            question: 'Generate prioritized action items and next steps.',
            refresh_context: false,
            max_plan_steps: 8,
            retrieval_k: 6
          },
          { token, apiBase }
        );
        if (!ignore) {
          setPlan(res);
        }
      } catch (err) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to generate plan');
        }
      } finally {
        if (!ignore) {
          setPending(false);
        }
      }
    }
    void runPlan();
    return () => {
      ignore = true;
    };
  }, [feed, summary, apiBase, token]);

  if (!feed || !summary) {
    return (
      <div className="rounded-3xl border border-dashed border-white/15 p-6 text-sm text-slate-400">
        Ingest a workbook or select a feed to see automated action items.
      </div>
    );
  }

  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
      <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Action plan</p>
      <h3 className="mt-1 text-lg font-semibold text-white">{feed.name}</h3>
      {pending && <p className="mt-3 text-sm text-slate-400">Agents preparing action items…</p>}
      {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}
      {plan && !error && (
        <div className="mt-4 space-y-3 text-sm text-slate-100">
          {(plan.completed || []).slice(0, 4).map((step, idx) => (
            <div key={idx} className="rounded-2xl border border-white/10 bg-black/30 p-3">
              <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Step {idx + 1}</p>
              <pre className="mt-2 whitespace-pre-wrap text-slate-100">{JSON.stringify(step, null, 2)}</pre>
            </div>
          ))}
          {!plan.completed?.length && plan.answer && (
            <p className="rounded-2xl border border-white/10 bg-black/30 p-3 text-sm text-slate-100">
              {plan.answer}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
