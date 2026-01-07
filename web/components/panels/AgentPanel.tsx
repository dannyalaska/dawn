'use client';

import { useCallback, useEffect, useState } from 'react';
import { SparklesIcon, CheckCircleIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import useDawnData from '@/hooks/useDawnData';
import AgentRunLog from '@/components/panels/AgentRunLog';
import { fetchFeeds, runAgents } from '@/lib/api';
import type { AgentRunSummary, FeedRecord } from '@/lib/types';
import { useDawnSession } from '@/context/dawn-session';

interface AgentPanelProps {
  activeFeedId?: string | null;
  onRun?: (result: AgentRunSummary) => void;
}

export default function AgentPanel({ activeFeedId, onRun }: AgentPanelProps) {
  const { token, apiBase } = useDawnSession();
  const feeds = useDawnData(['feeds'], ({ token, apiBase }) => fetchFeeds({ token, apiBase }));
  const [selected, setSelected] = useState<string>(activeFeedId || '');
  const [question, setQuestion] = useState<string>('Summarize anomalies and key metrics.');
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<AgentRunSummary | null>(null);
  const [error, setError] = useState('');
  const [lastRunFeed, setLastRunFeed] = useState<string | null>(null);

  const executeRun = useCallback(
    async (feedId?: string, auto = false) => {
      const target = feedId || selected;
      if (!target) {
        setError('Select a feed before running agents');
        return;
      }
      setPending(true);
      setError('');
      try {
        const res = await runAgents(
          {
            feed_identifier: target,
            question,
            refresh_context: true,
            max_plan_steps: 12,
            retrieval_k: 8
          },
          { token, apiBase }
        );
        setResult(res);
        setLastRunFeed(target);
        onRun?.(res);
      } catch (err) {
        if (!auto) {
          setError(err instanceof Error ? err.message : 'Agent run failed');
        } else {
          console.error(err);
        }
      } finally {
        setPending(false);
      }
    },
    [selected, question, token, apiBase, onRun]
  );

  useEffect(() => {
    if (!activeFeedId || pending) {
      return;
    }
    setSelected(activeFeedId);
    if (activeFeedId !== lastRunFeed) {
      void executeRun(activeFeedId, true);
    }
  }, [activeFeedId, lastRunFeed, pending, executeRun]);

  const feedList = (feeds.data ?? []) as FeedRecord[];

  return (
    <div className="glass-panel rounded-3xl p-6 space-y-4">
      <div className="flex items-center gap-2">
        <div className="rounded-lg bg-pink-500/10 p-2">
          <SparklesIcon className="h-5 w-5 text-pink-400" />
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Agent swarm</p>
          <h3 className="text-lg font-semibold text-white">Deep verification</h3>
        </div>
      </div>

      <div className="space-y-3">
        <label className="block text-sm text-slate-200">
          <span className="text-xs uppercase tracking-[0.3em] text-slate-500 mb-2 block">Select Feed</span>
          <select
            className="w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm focus:border-sky-400 focus:ring-2 focus:ring-sky-400/20"
            value={selected}
            onChange={(event) => setSelected(event.target.value)}
          >
            <option value="">Choose a feed…</option>
            {feedList.map((feed) => (
              <option key={feed.identifier} value={feed.identifier}>
                {feed.name}
              </option>
            ))}
          </select>
        </label>

        <label className="block text-sm text-slate-200">
          <span className="text-xs uppercase tracking-[0.3em] text-slate-500 mb-2 block">Question (optional)</span>
          <input
            className="w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm focus:border-sky-400 focus:ring-2 focus:ring-sky-400/20"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="What insights should the agents find?"
          />
        </label>

        <button
          type="button"
          onClick={() => executeRun()}
          disabled={!selected || pending}
          className="w-full rounded-full bg-gradient-to-r from-pink-500 via-pink-400 to-rose-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-pink-500/25 hover:shadow-xl disabled:opacity-50 transition-all flex items-center justify-center gap-2"
        >
          <SparklesIcon className={`h-4 w-4 ${pending ? 'animate-spin-slow' : ''}`} />
          {pending ? 'Agents running…' : 'Run agents'}
        </button>
      </div>

      {/* Error state */}
      {error && (
        <div className="flex gap-2 rounded-lg bg-rose-500/10 border border-rose-500/20 p-3">
          <ExclamationTriangleIcon className="h-5 w-5 text-rose-400 flex-shrink-0" />
          <p className="text-sm text-rose-300">{error}</p>
        </div>
      )}

      {/* Result display */}
      {result && (
        <div className="space-y-3 border-t border-white/10 pt-4">
          <div className="flex items-start gap-2">
            <CheckCircleIcon className="h-5 w-5 text-emerald-400 flex-shrink-0 mt-1" />
            <div>
              <p className="text-sm font-semibold text-slate-100">{result.answer || 'Analysis complete.'}</p>
              <p className="text-xs text-slate-400 mt-1">
                {result.completed?.length || 0} tasks completed
              </p>
            </div>
          </div>

          {result.warnings?.length > 0 && (
            <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 p-3">
              <p className="text-xs uppercase tracking-[0.2em] text-amber-400 font-semibold mb-2">⚠️ Warnings</p>
              <ul className="space-y-1">
                {result.warnings.map((warning, idx) => (
                  <li key={idx} className="text-xs text-amber-200">{warning}</li>
                ))}
              </ul>
            </div>
          )}

          {result.plan?.length > 0 && (
            <details className="rounded-lg border border-white/10 bg-black/30 p-3">
              <summary className="cursor-pointer text-xs uppercase tracking-[0.3em] text-slate-400 font-semibold">
                Execution Plan ({result.plan.length} steps)
              </summary>
              <div className="mt-2 space-y-2 text-xs">
                {result.plan.map((step, idx) => (
                  <div key={idx} className="text-slate-300">
                    <p className="font-semibold text-slate-200">Step {idx + 1}</p>
                    <pre className="text-slate-500 text-[10px] mt-1 overflow-auto max-h-20">
                      {JSON.stringify(step, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            </details>
          )}

          {result.run_log?.length > 0 && (
            <div>
              <AgentRunLog log={result.run_log} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
