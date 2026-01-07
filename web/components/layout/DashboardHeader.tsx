'use client';

import { useMemo } from 'react';
import Image from 'next/image';
import { SparklesIcon, ArrowPathIcon } from '@heroicons/react/24/outline';
import type { PreviewTable, IndexExcelResponse, AgentRunSummary } from '@/lib/types';

interface DashboardHeaderProps {
  preview?: PreviewTable | null;
  profile?: IndexExcelResponse | null;
  agentResult?: AgentRunSummary | null;
  onRefresh?: () => void;
  isLoading?: boolean;
}

export default function DashboardHeader({
  preview,
  profile,
  agentResult,
  onRefresh,
  isLoading
}: DashboardHeaderProps) {
  const workflowStage = useMemo(() => {
    if (agentResult) return { stage: 'Agents & Chat', color: 'text-pink-400' };
    if (profile) return { stage: 'Analysis Complete', color: 'text-emerald-400' };
    if (preview) return { stage: 'Ready to Index', color: 'text-amber-400' };
    return { stage: 'Upload a workbook', color: 'text-slate-400' };
  }, [preview, profile, agentResult]);

  const dataInfo = useMemo(() => {
    if (!profile) return null;
    return {
      source: profile.source,
      sheet: profile.sheet,
      rows: profile.rows,
      chunks: profile.indexed_chunks
    };
  }, [profile]);

  return (
    <div className="relative">
      {/* Background accent */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-amber-500/5 via-pink-500/5 to-transparent blur-2xl" />

      <div className="relative space-y-6">
        {/* Top bar */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Image
              src="/dawn_logo.png"
              alt="Dawn"
              width={40}
              height={40}
              className="h-10 w-10 rounded-full object-contain"
            />
            <div>
              <h1 className="text-2xl font-bold text-slate-100">Dawn Horizon</h1>
              <p className={`text-sm font-medium ${workflowStage.color}`}>
                {workflowStage.stage}
              </p>
            </div>
          </div>

          <button
            onClick={onRefresh}
            disabled={isLoading}
            className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-slate-200 hover:bg-white/10 disabled:opacity-50 transition-all"
          >
            <ArrowPathIcon className={`h-4 w-4 ${isLoading ? 'animate-spin-slow' : ''}`} />
            Refresh
          </button>
        </div>

        {/* Data info card */}
        {dataInfo && (
          <div className="glass-panel rounded-2xl p-4">
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div className="flex items-center gap-3">
                <div className="rounded-lg bg-amber-500/10 p-2">
                  <SparklesIcon className="h-5 w-5 text-amber-400" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Active Dataset</p>
                  <p className="text-lg font-semibold text-slate-100 mt-1">
                    {dataInfo.source}
                    {dataInfo.sheet && ` · ${dataInfo.sheet}`}
                  </p>
                </div>
              </div>

              <div className="flex gap-4">
                <div className="text-right">
                  <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Rows</p>
                  <p className="text-lg font-bold text-slate-100 mt-1">
                    {dataInfo.rows.toLocaleString()}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-xs uppercase tracking-[0.3em] text-slate-500">Context Chunks</p>
                  <p className="text-lg font-bold text-slate-100 mt-1">
                    {dataInfo.chunks}
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
