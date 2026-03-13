'use client';

import { useMemo } from 'react';
import { ArrowRightIcon } from '@heroicons/react/24/outline';
import useDawnData from '@/hooks/useDawnData';
import { fetchFeeds } from '@/lib/api';
import type { FeedRecord } from '@/lib/types';
import clsx from 'clsx';

interface FeedGalleryProps {
  onSelectSource?: (source: string) => void;
  onSelectFeed?: (payload: { feed: FeedRecord; source: string | null }) => void;
  activeSource?: string | null;
  activeFeedId?: string | null;
}

function deriveSource(feed: FeedRecord): string | null {
  const sheet = feed.latest_version?.sheet || feed.latest_version?.summary?.sheet;
  if (!sheet) return null;
  return `${feed.name ?? feed.identifier}:${sheet}`;
}

export default function FeedGallery({
  onSelectSource,
  onSelectFeed,
  activeSource,
  activeFeedId
}: FeedGalleryProps) {
  const { data, error, isLoading } = useDawnData(['feeds'], ({ token, apiBase }) =>
    fetchFeeds({ token, apiBase })
  );

  const feeds = useMemo(() => data ?? [], [data]);
  const derivedSources = useMemo(() => new Map(feeds.map((feed) => [feed.identifier, deriveSource(feed)])), [feeds]);

  if (isLoading) {
    return <div className="text-sm text-slate-400">Fetching feeds…</div>;
  }

  if (error) {
    return <div className="text-sm text-rose-400">Unable to load feeds: {error.message}</div>;
  }

  if (!feeds.length) {
    return <div className="text-sm text-slate-400">No feeds yet. Upload a workbook to see it light up here.</div>;
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
      {feeds.map((feed) => {
        const latest = feed.latest_version;
        const sourceHint = derivedSources.get(feed.identifier);
        const isActive =
          (activeSource && sourceHint && activeSource === sourceHint) ||
          (activeFeedId && activeFeedId === feed.identifier);
        const tags = (latest?.summary?.tags as string[] | undefined) ?? [];
        const dq = (latest?.summary as Record<string, unknown> | undefined)?.dq as
          | { status: string; pass: number; fail: number; total: number }
          | undefined;
        const dqBadge = dq
          ? dq.status === 'pass'
            ? { label: `DQ ${dq.pass}/${dq.total}`, classes: 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/25' }
            : dq.status === 'fail'
            ? { label: `DQ ${dq.fail} fail`, classes: 'bg-rose-500/15 text-rose-300 border border-rose-500/25' }
            : { label: 'DQ skip', classes: 'bg-white/5 text-slate-400 border border-white/10' }
          : null;
        return (
          <button
            type="button"
            key={feed.identifier}
            className={clsx(
              'group flex flex-col rounded-3xl border border-white/10 bg-white/5 p-5 text-left transition focus:outline-none',
              isActive && 'border-amber-300/60 bg-amber-300/10'
            )}
            onClick={() => {
              if (sourceHint) {
                onSelectSource?.(sourceHint);
              }
              onSelectFeed?.({ feed, source: sourceHint });
            }}
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.3em] text-slate-400">{feed.identifier}</p>
                <p className="text-xl font-semibold text-white">{feed.name}</p>
              </div>
              <div className="flex items-center gap-2">
                {dqBadge && (
                  <span className={clsx('rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.06em]', dqBadge.classes)}>
                    {dqBadge.label}
                  </span>
                )}
                <ArrowRightIcon className="h-5 w-5 text-slate-400 transition group-hover:translate-x-1 group-hover:text-white" />
              </div>
            </div>
            {latest && (
              <dl className="mt-4 grid grid-cols-3 gap-3 text-center">
                <div>
                  <dt className="text-[11px] uppercase tracking-[0.3em] text-slate-500">Rows</dt>
                  <dd className="text-lg font-semibold">{latest.rows?.toLocaleString() ?? '—'}</dd>
                </div>
                <div>
                  <dt className="text-[11px] uppercase tracking-[0.3em] text-slate-500">Columns</dt>
                  <dd className="text-lg font-semibold">{latest.columns ?? '—'}</dd>
                </div>
                <div>
                  <dt className="text-[11px] uppercase tracking-[0.3em] text-slate-500">Version</dt>
                  <dd className="text-lg font-semibold">v{latest.number ?? '1'}</dd>
                </div>
              </dl>
            )}
            {sourceHint && (
              <p className="mt-4 text-xs text-amber-200">source key · {sourceHint}</p>
            )}
            {tags.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {tags.map((tag) => (
                  <span key={tag} className="rounded-full bg-white/5 px-3 py-1 text-xs capitalize text-slate-300">
                    {tag.replace(/[-_]/g, ' ')}
                  </span>
                ))}
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}
