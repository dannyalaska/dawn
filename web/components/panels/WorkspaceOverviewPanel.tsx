'use client';

import { useState } from 'react';
import { resetWorkspace } from '@/lib/api';
import { useDawnSession } from '@/context/dawn-session';
import type { FeedRecord, IndexExcelResponse, PreviewTable } from '@/lib/types';
import { useSWRConfig } from 'swr';

interface WorkspaceOverviewPanelProps {
  preview: PreviewTable | null;
  summary: IndexExcelResponse | null;
  activeFeed: FeedRecord | null;
}

const StatCard = ({ label, value, helper }: { label: string; value: string; helper?: string }) => (
  <div className="rounded-2xl border border-white/10 bg-black/30 p-4">
    <p className="text-xs uppercase tracking-[0.3em] text-slate-400">{label}</p>
    <p className="mt-2 text-xl font-semibold text-white">{value}</p>
    {helper && <p className="mt-1 text-xs text-slate-400">{helper}</p>}
  </div>
);

export default function WorkspaceOverviewPanel({ preview, summary, activeFeed }: WorkspaceOverviewPanelProps) {
  const { token, apiBase } = useDawnSession();
  const { mutate } = useSWRConfig();
  const [resetText, setResetText] = useState('');
  const [resetStatus, setResetStatus] = useState('');
  const [resetPending, setResetPending] = useState(false);

  const hasData = Boolean(preview || summary || activeFeed);

  const handleReset = async () => {
    if (resetText.trim().toUpperCase() !== 'RESET') {
      setResetStatus('Type RESET to confirm.');
      return;
    }
    setResetPending(true);
    setResetStatus('Clearing workspace…');
    try {
      await resetWorkspace({ confirm: true }, { token, apiBase });
      setResetStatus('Workspace cleared. Refreshing data…');
      setResetText('');
      window.dispatchEvent(new Event('workspace:reset'));
      mutate(() => true, undefined, { revalidate: true }).catch(() => undefined);
    } catch (err) {
      setResetStatus(err instanceof Error ? err.message : 'Workspace reset failed.');
    } finally {
      setResetPending(false);
    }
  };

  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
      <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Workspace status</p>
      <h3 className="mt-1 text-lg font-semibold text-white">Ingestion snapshot</h3>
      {!hasData && (
        <p className="mt-3 text-sm text-slate-400">
          Upload or select a feed to unlock contextual stats, tags, and agent plans.
        </p>
      )}
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        {preview && (
          <StatCard
            label={`Preview · ${preview.sheet}`}
            value={`${preview.shape[0].toLocaleString()} rows · ${preview.shape[1]} cols`}
            helper={preview.sheet_names ? `${preview.sheet_names.length} sheets detected` : undefined}
          />
        )}
        {summary && (
          <StatCard
            label="Context"
            value={`${summary.indexed_chunks ?? summary.rows ?? ''} chunks`}
            helper={summary.summary?.tags?.slice(0, 3).join(', ') || 'Ready for retrieval'}
          />
        )}
        {activeFeed && (
          <StatCard
            label="Active feed"
            value={activeFeed.name}
            helper={`Identifier ${activeFeed.identifier}`}
          />
        )}
        {!preview && <StatCard label="Preview" value="Pending" helper="Upload workbook to inspect rows" />}
        {!summary && <StatCard label="Context" value="Not indexed" helper="Send to Dawn to chunk and tag" />}
        {!activeFeed && <StatCard label="Active feed" value="None" helper="Register or select a feed" />}
      </div>

      <div className="mt-6 rounded-2xl border border-rose-400/30 bg-rose-500/10 p-4">
        <p className="text-xs uppercase tracking-[0.3em] text-rose-200">Danger zone</p>
        <p className="mt-2 text-xs text-rose-100/80">
          This clears feeds, uploads, context memory, and materialized tables for your account.
        </p>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
          <input
            value={resetText}
            onChange={(event) => setResetText(event.target.value)}
            placeholder="Type RESET"
            className="w-full rounded-2xl border border-rose-400/30 bg-black/40 px-3 py-2 text-xs uppercase tracking-[0.3em] text-rose-100 placeholder:text-rose-200/40"
          />
          <button
            type="button"
            onClick={handleReset}
            disabled={resetPending}
            className="inline-flex items-center justify-center rounded-full border border-rose-400/40 px-4 py-2 text-[11px] uppercase tracking-[0.3em] text-rose-100 disabled:opacity-50"
          >
            {resetPending ? 'Clearing…' : 'Clear workspace'}
          </button>
        </div>
        {resetStatus && <p className="mt-2 text-xs text-rose-100/80">{resetStatus}</p>}
      </div>
    </div>
  );
}
