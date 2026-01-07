'use client';

import { FormEvent, useState } from 'react';
import { CloudIcon } from '@heroicons/react/24/outline';
import { ingestFeed } from '@/lib/api';
import { useDawnSession } from '@/context/dawn-session';
import { useSWRConfig } from 'swr';

export default function FeedIngestPanel() {
  const { token, apiBase } = useDawnSession();
  const { mutate } = useSWRConfig();
  const [identifier, setIdentifier] = useState('support_copilot');
  const [name, setName] = useState('Support Copilot');
  const [sheet, setSheet] = useState('Tickets');
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState('Add a feed to enable autonomous analysis.');
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setStatus('Please attach a workbook.');
      return;
    }
    setPending(true);
    setStatus('Ingesting feed…');
    try {
      const form = new FormData();
      form.append('identifier', identifier.trim());
      form.append('name', name.trim());
      form.append('source_type', 'upload');
      if (sheet) {
        form.append('sheet', sheet.trim());
      }
      form.append('file', file);
      await ingestFeed(form, { token, apiBase });
      setStatus(`Feed ${identifier} ready.`);
      mutate(['feeds', token, apiBase], undefined, { revalidate: true }).catch(() => undefined);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Feed ingest failed');
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
      <div className="flex items-center gap-3 text-slate-200">
        <CloudIcon className="h-5 w-5" />
        <div>
          <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Feeds</p>
          <h3 className="text-lg font-semibold text-white">Register workbook</h3>
        </div>
      </div>
      <form className="mt-4 space-y-3" onSubmit={handleSubmit}>
        <label className="block text-sm text-slate-200">
          Identifier
          <input
            className="mt-1 w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm"
            value={identifier}
            onChange={(event) => setIdentifier(event.target.value)}
          />
        </label>
        <label className="block text-sm text-slate-200">
          Name
          <input
            className="mt-1 w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label className="block text-sm text-slate-200">
          Favorite sheet
          <input
            className="mt-1 w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm"
            value={sheet}
            onChange={(event) => setSheet(event.target.value)}
          />
        </label>
        <label className="block text-sm text-slate-200">
          Workbook
          <input
            type="file"
            accept=".xlsx,.xls,.xlsm"
            className="mt-1 block w-full text-xs text-slate-300"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <button
          type="submit"
          disabled={pending}
          className="rounded-full bg-gradient-to-r from-amber-400 via-pink-500 to-sky-500 px-4 py-2 text-sm font-semibold text-slate-900 shadow-aurora disabled:opacity-50"
        >
          {pending ? 'Registering…' : 'Register feed'}
        </button>
      </form>
      <p className="mt-3 text-xs text-slate-400">{status}</p>
    </div>
  );
}
