'use client';

import type { FeedRecord, IndexExcelResponse, PreviewTable } from '@/lib/types';

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
  if (!preview && !summary && !activeFeed) {
    return (
      <div className="rounded-3xl border border-dashed border-white/20 bg-white/5 p-6 text-sm text-slate-400">
        Upload or select a feed to unlock contextual stats, tags, and agent plans.
      </div>
    );
  }

  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
      <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Workspace status</p>
      <h3 className="mt-1 text-lg font-semibold text-white">Ingestion snapshot</h3>
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
    </div>
  );
}
