'use client';

import useDawnData from '@/hooks/useDawnData';
import { fetchJobs, runJob, pauseJob, resumeJob } from '@/lib/api';
import type { JobRecord } from '@/lib/types';
import { useDawnSession } from '@/context/dawn-session';

export default function JobsPanel() {
  const { token, apiBase } = useDawnSession();
  const jobs = useDawnData(['jobs'], ({ token, apiBase }) => fetchJobs({ token, apiBase }));
  const list = (jobs.data ?? []) as JobRecord[];

  async function trigger(action: 'run' | 'pause' | 'resume', id: number) {
    try {
      if (action === 'run') {
        await runJob(id, { token, apiBase });
      } else if (action === 'pause') {
        await pauseJob(id, { token, apiBase });
      } else {
        await resumeJob(id, { token, apiBase });
      }
      jobs.mutate();
    } catch (err) {
      console.error(err);
    }
  }

  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
      <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Jobs &amp; automation</p>
      <h3 className="mt-1 text-lg font-semibold text-white">Scheduled workflows</h3>
      {jobs.isLoading && <p className="mt-4 text-sm text-slate-400">Loading jobs…</p>}
      {!jobs.isLoading && list.length === 0 && (
        <p className="mt-4 text-sm text-slate-400">No jobs configured yet.</p>
      )}
      <div className="mt-4 space-y-3">
        {list.map((job) => (
          <div key={job.id} className="rounded-2xl border border-white/10 bg-black/30 p-4 text-sm text-slate-200">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-base font-semibold text-white">{job.name}</p>
                <p className="text-xs text-slate-400">
                  Feed {job.feed_identifier} · Schedule {job.schedule || 'manual'}
                </p>
              </div>
              <div className="flex gap-2 text-xs">
                <button
                  type="button"
                  className="rounded-full border border-white/10 px-3 py-1"
                  onClick={() => trigger('run', job.id)}
                >
                  Run
                </button>
                <button
                  type="button"
                  className="rounded-full border border-white/10 px-3 py-1"
                  onClick={() => trigger(job.is_active ? 'pause' : 'resume', job.id)}
                >
                  {job.is_active ? 'Pause' : 'Resume'}
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
