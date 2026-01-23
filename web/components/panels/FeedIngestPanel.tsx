'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import { CloudIcon } from '@heroicons/react/24/outline';
import { ingestFeed } from '@/lib/api';
import { useDawnSession } from '@/context/dawn-session';
import { useSWRConfig } from 'swr';
import type { FeedRecord } from '@/lib/types';
import { suggestFeedMeta } from '@/lib/feed-utils';

const DEFAULT_IDENTIFIER = 'support_copilot';
const DEFAULT_NAME = 'Support Copilot';
const DEFAULT_SHEET = 'Tickets';

interface FeedIngestPanelProps {
  defaultFile?: File | null;
  defaultSheet?: string | null;
  sheetOptions?: string[];
  onFeedReady?: (feed: FeedRecord) => void;
}

export default function FeedIngestPanel({
  defaultFile,
  defaultSheet,
  sheetOptions = [],
  onFeedReady
}: FeedIngestPanelProps) {
  const { token, apiBase } = useDawnSession();
  const { mutate } = useSWRConfig();
  const [identifier, setIdentifier] = useState(DEFAULT_IDENTIFIER);
  const [name, setName] = useState(DEFAULT_NAME);
  const [sheet, setSheet] = useState(DEFAULT_SHEET);
  const [file, setFile] = useState<File | null>(null);
  const [fileSource, setFileSource] = useState<'latest' | 'manual' | null>(null);
  const [status, setStatus] = useState('Add a feed to enable autonomous analysis.');
  const [pending, setPending] = useState(false);

  const suggestedMeta = useMemo(() => suggestFeedMeta(defaultFile?.name, defaultSheet), [defaultFile, defaultSheet]);

  useEffect(() => {
    if (!defaultFile) return;
    if (file && fileSource !== 'latest') return;
    setFile(defaultFile);
    setFileSource('latest');
    if (identifier === DEFAULT_IDENTIFIER) {
      setIdentifier(suggestedMeta.identifier);
    }
    if (name === DEFAULT_NAME) {
      setName(suggestedMeta.name);
    }
    if (defaultSheet && sheet === DEFAULT_SHEET) {
      setSheet(defaultSheet);
    }
  }, [defaultFile, defaultSheet, file, fileSource, identifier, name, sheet, suggestedMeta]);

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
      const response = await ingestFeed(form, { token, apiBase });
      setStatus(`Feed ${identifier} ready.`);
      mutate(['feeds', token, apiBase], undefined, { revalidate: true }).catch(() => undefined);
      onFeedReady?.({
        identifier,
        name,
        source_type: response?.feed?.source_type || 'upload'
      });
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Feed ingest failed');
    } finally {
      setPending(false);
    }
  }

  const availableSheets = sheetOptions.length ? sheetOptions : defaultSheet ? [defaultSheet] : [];
  const showSheetSelect = availableSheets.length > 1;
  const showSheetInput = !showSheetSelect;

  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
      <div className="flex items-center gap-3 text-slate-200">
        <CloudIcon className="h-5 w-5" />
        <div>
          <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Feeds</p>
          <h3 className="text-lg font-semibold text-white">Register workbook</h3>
        </div>
      </div>
      {defaultFile && (
        <div className="mt-4 rounded-2xl border border-white/10 bg-black/30 p-3 text-xs text-slate-300">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="uppercase tracking-[0.3em] text-slate-400">Latest upload</p>
              <p className="mt-1 text-sm text-slate-200">{defaultFile.name}</p>
            </div>
            {fileSource === 'latest' ? (
              <button
                type="button"
                onClick={() => {
                  setFile(null);
                  setFileSource(null);
                }}
                className="rounded-full border border-white/10 px-3 py-1 text-[11px] uppercase tracking-[0.3em] text-slate-300"
              >
                Clear
              </button>
            ) : (
              <button
                type="button"
                onClick={() => {
                  setFile(defaultFile);
                  setFileSource('latest');
                  setIdentifier(suggestedMeta.identifier);
                  setName(suggestedMeta.name);
                  if (defaultSheet) setSheet(defaultSheet);
                }}
                className="rounded-full border border-white/10 px-3 py-1 text-[11px] uppercase tracking-[0.3em] text-amber-200"
              >
                Use latest upload
              </button>
            )}
          </div>
        </div>
      )}
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
        {showSheetInput && (
          <label className="block text-sm text-slate-200">
            Favorite sheet
            <input
              className="mt-1 w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm"
              value={sheet}
              onChange={(event) => setSheet(event.target.value)}
            />
          </label>
        )}
        {showSheetSelect && (
          <label className="block text-sm text-slate-200">
            Favorite sheet
            <select
              className="mt-1 w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm"
              value={sheet}
              onChange={(event) => setSheet(event.target.value)}
            >
              {availableSheets.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="block text-sm text-slate-200">
          Workbook
          <input
            type="file"
            accept=".xlsx,.xls,.xlsm"
            className="mt-1 block w-full text-xs text-slate-300"
            onChange={(event) => {
              const nextFile = event.target.files?.[0] ?? null;
              setFile(nextFile);
              setFileSource('manual');
              if (nextFile) {
                const suggestion = suggestFeedMeta(nextFile.name, sheet);
                if (identifier === DEFAULT_IDENTIFIER) {
                  setIdentifier(suggestion.identifier);
                }
                if (name === DEFAULT_NAME) {
                  setName(suggestion.name);
                }
              }
            }}
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
