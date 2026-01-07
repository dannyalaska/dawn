'use client';

import { PlayIcon } from '@heroicons/react/24/outline';
import useDawnData from '@/hooks/useDawnData';
import { fetchRunnerMeta, fetchSchedulerStatus } from '@/lib/api';

export default function RunnerMiniPanel() {
  const runner = useDawnData(['runner-meta'], ({ token, apiBase }) => fetchRunnerMeta({ token, apiBase }));
  const scheduler = useDawnData(['scheduler-status'], ({ token, apiBase }) => fetchSchedulerStatus({ token, apiBase }));

  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Runner</p>
          <h3 className="text-lg font-semibold text-white">Scheduler pulse</h3>
        </div>
        <PlayIcon className="h-5 w-5 text-emerald-300" />
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm text-slate-200">
        <div>
          <dt className="text-[11px] uppercase tracking-[0.3em] text-slate-500">Jobs</dt>
          <dd className="text-lg font-semibold">{runner.data?.jobs.total ?? '—'}</dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-[0.3em] text-slate-500">Runs</dt>
          <dd className="text-lg font-semibold">{runner.data?.runs.total ?? '—'}</dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-[0.3em] text-slate-500">Active</dt>
          <dd className="text-lg font-semibold text-emerald-300">{runner.data?.jobs.active ?? 0}</dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-[0.3em] text-slate-500">Failed</dt>
          <dd className="text-lg font-semibold text-rose-300">{runner.data?.runs.failed ?? 0}</dd>
        </div>
      </dl>
      <p className="mt-4 text-xs text-slate-400">
        {scheduler.data?.running ? 'Scheduler online' : 'Scheduler paused'} · {scheduler.data?.count ?? 0} scheduled
        jobs
      </p>
    </div>
  );
}
