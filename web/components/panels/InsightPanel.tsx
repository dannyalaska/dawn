'use client';

import type { IndexExcelResponse } from '@/lib/types';

interface InsightPanelProps {
  summary: IndexExcelResponse['summary'] | null | undefined;
}

export default function InsightPanel({ summary }: InsightPanelProps) {
  if (!summary) {
    return (
      <div className="rounded-3xl border border-dashed border-white/15 p-6 text-sm text-slate-400">
        Run "Send to Dawn" to generate deterministic metrics and rich tags.
      </div>
    );
  }

  const metrics = (summary.metrics ?? []).slice(0, 3);
  const tags = summary.tags?.slice(0, 8) ?? [];

  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
      <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Metrics &amp; tags</p>
      <h3 className="mt-1 text-lg font-semibold text-white">Dawn highlights</h3>
      {tags.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {tags.map((tag) => (
            <span key={tag} className="rounded-full bg-white/5 px-3 py-1 text-xs uppercase tracking-[0.3em] text-slate-200">
              {tag}
            </span>
          ))}
        </div>
      )}
      <div className="mt-4 space-y-3">
        {metrics.map((metric, idx) => (
          <div key={idx} className="rounded-2xl border border-white/10 bg-black/30 px-3 py-3">
            <p className="text-xs uppercase tracking-[0.3em] text-slate-400">{metric.description || metric.column}</p>
            <div className="mt-2 flex flex-wrap gap-4 text-sm text-slate-100">
              {(metric.values || []).slice(0, 3).map((value) => (
                <span key={value.label} className="font-semibold">
                  {value.label}: {value.count}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
      {(!metrics || metrics.length === 0) && (
        <p className="mt-4 text-sm text-slate-300">No aggregate metrics generated yet.</p>
      )}
    </div>
  );
}
