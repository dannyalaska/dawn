'use client';

import { ChangeEvent, useMemo, useState } from 'react';
import { CloudArrowUpIcon, EyeIcon, ServerStackIcon, CheckCircleIcon } from '@heroicons/react/24/outline';
import { useSWRConfig } from 'swr';
import { ingestWorkbook, previewWorkbook } from '@/lib/api';
import { useDawnSession } from '@/context/dawn-session';
import type { IndexExcelResponse, PreviewTable } from '@/lib/types';

interface UploadPanelProps {
  onPreviewed?: (preview: PreviewTable | null) => void;
  onProfiled?: (sourceKey: string | null, profile: IndexExcelResponse | null) => void;
}

export default function UploadPanel({ onPreviewed, onProfiled }: UploadPanelProps) {
  const { token, apiBase } = useDawnSession();
  const { mutate } = useSWRConfig();
  const [file, setFile] = useState<File | null>(null);
  const [sheet, setSheet] = useState<string>('');
  const [sheetOptions, setSheetOptions] = useState<string[]>([]);
  const [chunkSize, setChunkSize] = useState(600);
  const [overlap, setOverlap] = useState(80);
  const [status, setStatus] = useState('Pick a workbook to start.');
  const [previewPending, setPreviewPending] = useState(false);
  const [indexPending, setIndexPending] = useState(false);
  const [lastPreview, setLastPreview] = useState<PreviewTable | null>(null);
  const [lastProfile, setLastProfile] = useState<IndexExcelResponse | null>(null);
  const [isDragActive, setIsDragActive] = useState(false);

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const nextFile = event.target.files?.[0] ?? null;
    processFile(nextFile);
  }

  function handleDrag(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    event.stopPropagation();
    if (event.type === 'dragenter' || event.type === 'dragover') {
      setIsDragActive(true);
    } else if (event.type === 'dragleave') {
      setIsDragActive(false);
    }
  }

  function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    event.stopPropagation();
    setIsDragActive(false);
    const nextFile = event.dataTransfer.files?.[0] ?? null;
    processFile(nextFile);
  }

  function processFile(nextFile: File | null) {
    setFile(nextFile);
    setSheet('');
    setSheetOptions([]);
    setLastPreview(null);
    setLastProfile(null);
    setStatus(nextFile ? `Ready to preview ${nextFile.name}` : 'Pick a workbook to start.');
    onPreviewed?.(null);
    onProfiled?.(null, null);
  }

  async function handlePreview() {
    if (!file) {
      setStatus('Choose a workbook before previewing.');
      return;
    }
    setPreviewPending(true);
    setStatus('Generating preview…');
    try {
      const form = new FormData();
      form.append('file', file);
      if (sheet) {
        form.append('sheet', sheet);
      }
      const result = await previewWorkbook(form, { token, apiBase });
      setLastPreview(result);
      onPreviewed?.(result);
      setSheet(result.sheet ?? sheet);
      setSheetOptions(result.sheet_names ?? []);
      setStatus(`Previewing ${result.sheet} · ${result.shape[0].toLocaleString()} rows`);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Preview failed');
    } finally {
      setPreviewPending(false);
    }
  }

  async function handleIndex() {
    if (!file) {
      setStatus('Choose a workbook before indexing.');
      return;
    }
    setIndexPending(true);
    setStatus('Sending to Dawn…');
    try {
      const form = new FormData();
      form.append('file', file);
      if (sheet) {
        form.append('sheet', sheet);
      }
      form.append('chunk_max_chars', String(chunkSize));
      form.append('chunk_overlap', String(overlap));
      const result = await ingestWorkbook(form, { token, apiBase });
      setLastProfile(result);
      const canonicalSource = result.sheet ? `${result.source}:${result.sheet}` : result.source;
      setStatus(`✓ Indexed ${canonicalSource}. Context ready.`);
      mutate(['feeds', token, apiBase], undefined, { revalidate: true }).catch(() => undefined);
      onProfiled?.(canonicalSource || null, result);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Index failed');
    } finally {
      setIndexPending(false);
    }
  }

  const sheetChoices = useMemo(() => {
    if (!sheetOptions.length) return null;
    return (
      <label className="flex flex-col text-sm text-slate-200">
        <span className="text-xs uppercase tracking-[0.3em] text-slate-500">Sheet</span>
        <select
          value={sheet || sheetOptions[0]}
          onChange={(event) => setSheet(event.target.value)}
          className="mt-2 rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm focus:border-sky-400 focus:ring-2 focus:ring-sky-400/20"
        >
          {sheetOptions.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>
    );
  }, [sheet, sheetOptions]);

  return (
    <div className="glass-panel rounded-3xl p-6 space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Upload</p>
          <h3 className="text-2xl font-bold text-slate-100 mt-2">Stream workbook into Dawn</h3>
        </div>
        {lastProfile && (
          <span className="inline-flex items-center gap-2 rounded-full bg-emerald-500/10 border border-emerald-500/30 px-3 py-1 text-xs text-emerald-400">
            <CheckCircleIcon className="h-4 w-4" />
            Indexed
          </span>
        )}
      </div>

      {/* Drag and drop area */}
      <label
        className={`block cursor-pointer rounded-3xl border-2 transition-all ${
          isDragActive
            ? 'border-amber-300 bg-amber-400/20 shadow-lg'
            : 'border-dashed border-amber-300/70 hover:border-amber-200 bg-gradient-to-r from-amber-400/10 via-pink-500/5 to-sky-400/10 hover:from-amber-400/20 hover:via-pink-500/15 hover:to-sky-400/20'
        } p-6 sm:p-8 shadow-md transition-all duration-200`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <input type="file" accept=".xlsx,.xls,.xlsm" className="hidden" onChange={handleFileChange} />
        <div className="flex flex-col items-center justify-center gap-3 text-center">
          <div className="rounded-full bg-white/10 p-3">
            <CloudArrowUpIcon className="h-8 w-8 text-amber-300" />
          </div>
          <div>
            <h4 className="text-lg font-semibold text-white">
              {file ? file.name : 'Drop your workbook here'}
            </h4>
            <p className="text-sm text-slate-400 mt-1">
              {file ? 'Ready to preview' : 'or click to browse (Excel, CSV)'}
            </p>
          </div>
        </div>
      </label>

      {/* Status indicator */}
      <p className={`text-sm font-medium ${
        status.includes('✓') ? 'text-emerald-400' :
        status.includes('failed') || status.includes('Failed') ? 'text-rose-400' :
        'text-slate-300'
      }`}>
        {status}
      </p>

      {/* Configuration */}
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="flex flex-col text-sm text-slate-200">
          <span className="text-xs uppercase tracking-[0.3em] text-slate-500 mb-2">Chunk size</span>
          <input
            type="number"
            value={chunkSize}
            onChange={(event) => setChunkSize(Number(event.target.value))}
            className="rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm focus:border-sky-400 focus:ring-2 focus:ring-sky-400/20"
          />
        </label>
        <label className="flex flex-col text-sm text-slate-200">
          <span className="text-xs uppercase tracking-[0.3em] text-slate-500 mb-2">Overlap</span>
          <input
            type="number"
            value={overlap}
            onChange={(event) => setOverlap(Number(event.target.value))}
            className="rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm focus:border-sky-400 focus:ring-2 focus:ring-sky-400/20"
          />
        </label>
        {sheetChoices}
      </div>

      {/* Action buttons */}
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={handlePreview}
          disabled={!file || previewPending}
          className="inline-flex items-center gap-2 rounded-full border border-white/20 hover:border-white/40 bg-white/5 hover:bg-white/10 px-4 py-2 text-sm font-medium text-slate-200 disabled:opacity-50 transition-all"
        >
          <EyeIcon className="h-4 w-4" />
          {previewPending ? 'Previewing…' : 'Preview'}
        </button>
        <button
          type="button"
          onClick={handleIndex}
          disabled={!file || indexPending}
          className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-amber-400 via-pink-500 to-sky-400 px-4 py-2 text-sm font-semibold text-slate-900 hover:shadow-lg hover:shadow-amber-500/25 disabled:opacity-50 transition-all"
        >
          <CloudArrowUpIcon className="h-4 w-4" />
          {indexPending ? 'Sending…' : 'Send to Dawn'}
        </button>
      </div>

      {/* Success state */}
      {lastProfile && (
        <div className="glass-panel-sm rounded-2xl p-4 border border-emerald-500/20 bg-emerald-500/5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-emerald-400/70 mb-1">Vectorized</p>
              <p className="text-lg font-semibold text-slate-100">
                {lastProfile.source}
                {lastProfile.sheet ? ` · ${lastProfile.sheet}` : ''}
              </p>
              <p className="text-xs text-slate-400 mt-1">{lastProfile.indexed_chunks} context chunks</p>
            </div>
            <span className="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-400">
              <ServerStackIcon className="h-4 w-4" />
              Redis ready
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
