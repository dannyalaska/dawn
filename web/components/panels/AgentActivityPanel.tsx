'use client';

import { ArrowPathIcon, ClockIcon, PlayIcon } from '@heroicons/react/24/outline';
import useDawnData from '@/hooks/useDawnData';
import { fetchRunnerMeta, fetchSchedulerStatus } from '@/lib/api';

function Metric({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
      <p className="text-[11px] uppercase tracking-[0.3em] text-slate-500">{label}</p>
      <p className={`mt-2 text-2xl font-semibold ${accent ?? 'text-white'}`}>{value}</p>
    </div>
  );
}

export default function AgentActivityPanel() {
  const runner = useDawnData(['runner-meta'], ({ token, apiBase }) => fetchRunnerMeta({ token, apiBase }));
  const scheduler = useDawnData(['scheduler'], ({ token, apiBase }) => fetchSchedulerStatus({ token, apiBase }));

  const lastRun = runner.data?.runs?.last_run;
  const jobBadges = (scheduler.data?.scheduled_jobs ?? []).slice(0, 4);

  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex-1">
          <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Agent swarm</p>
          <h3 className="mt-2 text-2xl font-semibold text-white">Runner &amp; scheduler pulse</h3>
        </div>
        <span className="inline-flex items-center gap-2 rounded-full border border-emerald-400/40 px-3 py-1 text-xs text-emerald-300">
          <PlayIcon className="h-3.5 w-3.5" />
          {scheduler.data?.running ? 'Scheduler online' : 'Scheduler paused'}
        </span>
      </div>
      <div className="mt-6 grid gap-4 lg:grid-cols-4">
        <Metric label="Jobs" value={runner.data?.jobs?.total?.toString() ?? '—'} />
        <Metric label="Active" value={runner.data?.jobs?.active?.toString() ?? '—'} accent="text-emerald-300" />
        <Metric label="Runs" value={runner.data?.runs?.total?.toString() ?? '—'} />
        <Metric label="Failed" value={runner.data?.runs?.failed?.toString() ?? '0'} accent="text-rose-300" />
      </div>
      <div className="mt-6 rounded-2xl border border-white/10 bg-black/40 p-4">
        <div className="flex flex-wrap items-center gap-3 text-sm text-slate-300">
          <ArrowPathIcon className="h-4 w-4" />
          Last run:&nbsp;
          {lastRun?.status ? (
            <>
              <span className="text-amber-200">{lastRun.status}</span>
              {lastRun.finished_at && <span>· {new Date(lastRun.finished_at).toLocaleString()}</span>}
              {lastRun.duration_seconds && <span>· {lastRun.duration_seconds}s</span>}
            </>
          ) : (
            'none yet'
          )}
        </div>
        {jobBadges.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            {jobBadges.map((job) => (
              <span key={job.job_id} className="inline-flex items-center gap-2 rounded-full border border-white/10 px-3 py-1">
                <ClockIcon className="h-3.5 w-3.5" />
                {job.name ?? `Job ${job.job_id}`}
                {job.next_run && <span className="text-slate-400">→ {new Date(job.next_run).toLocaleTimeString()}</span>}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
