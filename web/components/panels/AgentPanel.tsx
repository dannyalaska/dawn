'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { SparklesIcon, CheckCircleIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import useDawnData from '@/hooks/useDawnData';
import AgentRunLog from '@/components/panels/AgentRunLog';
import { fetchFeeds, ingestFeed, runAgents } from '@/lib/api';
import type { AgentRunSummary, FeedRecord } from '@/lib/types';
import { useDawnSession } from '@/context/dawn-session';
import { useSWRConfig } from 'swr';
import { suggestFeedMeta } from '@/lib/feed-utils';

interface AgentPanelProps {
  activeFeedId?: string | null;
  uploadFile?: File | null;
  uploadSheet?: string | null;
  onFeedReady?: (feed: FeedRecord) => void;
  onRun?: (result: AgentRunSummary) => void;
}

export default function AgentPanel({ activeFeedId, uploadFile, uploadSheet, onFeedReady, onRun }: AgentPanelProps) {
  const { token, apiBase } = useDawnSession();
  const { mutate } = useSWRConfig();
  const feeds = useDawnData(['feeds'], ({ token, apiBase }) => fetchFeeds({ token, apiBase }));
  const [selected, setSelected] = useState<string>(activeFeedId || '');
  const [question, setQuestion] = useState<string>('Summarize anomalies and key metrics.');
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<AgentRunSummary | null>(null);
  const [error, setError] = useState('');
  const [lastRunFeed, setLastRunFeed] = useState<string | null>(null);
  const [demoRunRequested, setDemoRunRequested] = useState(false);
  const [demoRunIdentifier, setDemoRunIdentifier] = useState<string | null>(null);
  const [demoSelectActive, setDemoSelectActive] = useState(false);
  const demoSelectTimerRef = useRef<NodeJS.Timeout | null>(null);
  const [demoRunActive, setDemoRunActive] = useState(false);
  const demoRunTimerRef = useRef<NodeJS.Timeout | null>(null);

  const runAgentsFor = useCallback(
    async (target: string, auto = false) => {
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
    },
    [apiBase, onRun, question, token]
  );

  const executeRun = useCallback(
    async (feedId?: string, auto = false) => {
      const target = feedId || selected;
      if (!target) {
        setError('Select a feed before running agents.');
        return;
      }
      setPending(true);
      setError('');
      try {
        await runAgentsFor(target, auto);
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
    [runAgentsFor, selected]
  );

  const handleRunLatestUpload = async () => {
    if (!uploadFile) {
      setError('Upload a workbook or select a feed before running agents.');
      return;
    }
    setPending(true);
    setError('');
    try {
      const { identifier, name } = suggestFeedMeta(uploadFile.name, uploadSheet);
      const form = new FormData();
      form.append('identifier', identifier);
      form.append('name', name);
      form.append('source_type', 'upload');
      if (uploadSheet) {
        form.append('sheet', uploadSheet);
      }
      form.append('file', uploadFile);
      await ingestFeed(form, { token, apiBase });
      mutate(['feeds', token, apiBase], undefined, { revalidate: true }).catch(() => undefined);
      onFeedReady?.({ identifier, name, source_type: 'upload' });
      setSelected(identifier);
      await runAgentsFor(identifier, true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Agent run failed');
    } finally {
      setPending(false);
    }
  };

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
  const demoOptions = feedList.length
    ? feedList.slice(0, 4).map((feed) => feed.name)
    : ['Support Tickets', 'Revenue Forecast', 'Ops Incidents', 'Customer Health'];

  const hasUpload = Boolean(uploadFile);

  useEffect(() => {
    const handleDemoRun = (event: Event) => {
      const customEvent = event as CustomEvent;
      const identifier = customEvent.detail?.identifier ?? null;
      setDemoRunIdentifier(identifier);
      setDemoRunRequested(true);
      setDemoSelectActive(true);
      setDemoRunActive(true);
      if (demoSelectTimerRef.current) {
        clearTimeout(demoSelectTimerRef.current);
      }
      demoSelectTimerRef.current = window.setTimeout(() => {
        setDemoSelectActive(false);
      }, 2400);
      if (demoRunTimerRef.current) {
        clearTimeout(demoRunTimerRef.current);
      }
      demoRunTimerRef.current = window.setTimeout(() => {
        setDemoRunActive(false);
      }, 3200);
    };

    window.addEventListener('demo:agent-trigger', handleDemoRun);
    return () => {
      window.removeEventListener('demo:agent-trigger', handleDemoRun);
    };
  }, []);

  useEffect(() => {
    return () => {
      if (demoSelectTimerRef.current) {
        clearTimeout(demoSelectTimerRef.current);
      }
      if (demoRunTimerRef.current) {
        clearTimeout(demoRunTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!demoRunRequested || pending) return;
    const directMatch = demoRunIdentifier
      ? feedList.find((feed) => feed.identifier === demoRunIdentifier)
      : null;
    const fallbackFeed = feedList[feedList.length - 1];
    const targetFeed = directMatch ?? fallbackFeed;
    if (!targetFeed) return;
    setSelected(targetFeed.identifier);
    setDemoRunRequested(false);
    void executeRun(targetFeed.identifier, true);
  }, [demoRunIdentifier, demoRunRequested, executeRun, feedList, pending]);

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
            className={`w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm focus:border-sky-400 focus:ring-2 focus:ring-sky-400/20 ${
              demoSelectActive ? 'ring-2 ring-amber-400/40' : ''
            }`}
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
          {demoSelectActive && (
            <div className="mt-3 rounded-2xl border border-amber-300/30 bg-amber-400/10 p-3 text-xs text-amber-100">
              <p className="uppercase tracking-[0.3em] text-amber-200">Auto-selecting feed</p>
              <div className="mt-2 space-y-1">
                {demoOptions.map((name) => (
                  <div
                    key={name}
                    className={`rounded-xl px-3 py-2 ${
                      name.toLowerCase().includes('support')
                        ? 'bg-amber-400/20 text-amber-50'
                        : 'bg-black/30 text-amber-100/80'
                    }`}
                  >
                    {name}
                  </div>
                ))}
              </div>
            </div>
          )}
        </label>

        {!selected && hasUpload && (
          <div className="rounded-2xl border border-amber-400/20 bg-amber-500/10 p-3 text-xs text-amber-100">
            <p className="uppercase tracking-[0.3em] text-amber-200">Latest upload detected</p>
            <p className="mt-2 text-sm text-amber-50">{uploadFile?.name}</p>
            {uploadSheet && (
              <p className="mt-1 text-[11px] text-amber-100/70">Sheet: {uploadSheet}</p>
            )}
            <button
              type="button"
              onClick={handleRunLatestUpload}
              disabled={pending}
              className="mt-3 inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-amber-400 via-pink-500 to-sky-500 px-4 py-2 text-xs font-semibold text-slate-900 shadow-aurora disabled:opacity-50"
            >
              <SparklesIcon className={`h-4 w-4 ${pending ? 'animate-spin-slow' : ''}`} />
              {pending ? 'Preparing…' : 'Create feed + run agents'}
            </button>
          </div>
        )}

        <label className="block text-sm text-slate-200">
          <span className="text-xs uppercase tracking-[0.3em] text-slate-500 mb-2 block">Question (optional)</span>
          <input
            className="w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm focus:border-sky-400 focus:ring-2 focus:ring-sky-400/20"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="What insights should the agents find?"
          />
        </label>

        {demoRunActive && (
          <div className="rounded-2xl border border-pink-400/30 bg-pink-500/10 p-3 text-xs text-pink-100">
            <div className="flex items-center gap-2 uppercase tracking-[0.3em] text-pink-200">
              <span className="h-2 w-2 rounded-full bg-pink-300 animate-pulse" />
              Agents running
            </div>
            <div className="mt-2 space-y-1 text-[11px] text-pink-100/80">
              <p>Scanning anomalies and spikes</p>
              <p>Cross-checking metrics and trends</p>
              <p>Summarizing executive takeaways</p>
            </div>
          </div>
        )}

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
