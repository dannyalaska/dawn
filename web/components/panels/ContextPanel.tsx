'use client';

import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import clsx from 'clsx';
import useDawnData from '@/hooks/useDawnData';
import { fetchContext } from '@/lib/api';
import type { ContextNote } from '@/lib/types';

interface ContextPanelProps {
  selectedSource?: string | null;
  onSourceChange?: (source: string) => void;
}

export default function ContextPanel({ selectedSource, onSourceChange }: ContextPanelProps) {
  const [source, setSource] = useState(selectedSource ?? '');

  useEffect(() => {
    if (selectedSource && selectedSource !== source) {
      setSource(selectedSource);
    }
  }, [selectedSource, source]);

  const swr = useDawnData(source ? ['context', source] : null, ({ token, apiBase }) =>
    fetchContext(source, 160, { token, apiBase })
  );

  const notes = swr.data?.notes ?? [];

  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
        <div className="flex-1">
          <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Context memory</p>
          <h3 className="mt-2 text-2xl font-semibold text-white">Recall the precise vector notes</h3>
        </div>
        <div className="flex flex-col gap-2 lg:w-96">
          <label className="text-xs uppercase tracking-[0.3em] text-slate-500">Source key</label>
          <input
            value={source}
            onChange={(event) => {
              const next = event.target.value;
              setSource(next);
              onSourceChange?.(next);
            }}
            placeholder="support_copilot.xlsx:Tickets"
            className="rounded-2xl border border-white/10 bg-black/40 px-4 py-2 text-sm text-white focus:border-amber-300 focus:outline-none"
          />
        </div>
      </div>
      <div className="mt-6 max-h-80 space-y-3 overflow-y-auto pr-3 scroll-soft">
        {!source && <p className="text-sm text-slate-500">Select a feed to stream its context memory.</p>}
        {source && swr.isLoading && <p className="text-sm text-slate-400">Loading context chunks…</p>}
        {source && swr.error && <p className="text-sm text-rose-400">{swr.error.message}</p>}
        {source && !swr.isLoading && notes.length === 0 && (
          <p className="text-sm text-slate-500">No context captured for this source yet.</p>
        )}
        <AnimatePresence>
          {notes.map((note) => (
            <motion.article
              layout
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.2 }}
              key={note.id}
              className={clsx(
                'rounded-2xl border border-white/10 bg-black/40 p-4 text-sm text-slate-200',
                note.type === 'summary' && 'border-amber-300/50 bg-amber-200/10 text-amber-50'
              )}
            >
              <p className="font-mono text-[11px] uppercase tracking-[0.4em] text-slate-500">
                #{note.row_index >= 0 ? note.row_index : note.type}
              </p>
              <p className="mt-2 whitespace-pre-wrap text-base leading-relaxed">{note.text}</p>
              {note.tags?.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {note.tags.slice(0, 4).map((tag) => (
                    <span key={tag} className="rounded-full bg-white/5 px-2 py-1 text-[11px] capitalize text-slate-300">
                      {tag.replace('column:', '')}
                    </span>
                  ))}
                </div>
              )}
            </motion.article>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
