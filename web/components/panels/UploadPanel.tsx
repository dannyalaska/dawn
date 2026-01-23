'use client';

import { ChangeEvent, useEffect, useMemo, useRef, useState } from 'react';
import { CloudArrowUpIcon, EyeIcon, ServerStackIcon, CheckCircleIcon } from '@heroicons/react/24/outline';
import { useSWRConfig } from 'swr';
import { ingestWorkbook, previewWorkbook } from '@/lib/api';
import { useDawnSession } from '@/context/dawn-session';
import type { IndexExcelResponse, PreviewTable } from '@/lib/types';

interface UploadPanelProps {
  onPreviewed?: (preview: PreviewTable | null) => void;
  onProfiled?: (sourceKey: string | null, profile: IndexExcelResponse | null) => void;
  onFileSelected?: (file: File | null) => void;
}

const DEMO_ROWS = [
  {
    ticket_id: 'TK-001',
    created_at: '2024-01-15 09:30',
    assigned_to: 'Alex Chen',
    resolved_by: 'Alex Chen',
    status: 'Closed',
    priority: 'High',
    category: 'Account',
    resolution_time_hours: 2.5,
    customer_name: 'Acme Corp',
    subject: 'Login not working'
  },
  {
    ticket_id: 'TK-002',
    created_at: '2024-01-15 10:15',
    assigned_to: 'Priya Sharma',
    resolved_by: 'Priya Sharma',
    status: 'Closed',
    priority: 'Medium',
    category: 'Billing',
    resolution_time_hours: 4.2,
    customer_name: 'Beta Inc',
    subject: 'Invoice discrepancy'
  },
  {
    ticket_id: 'TK-003',
    created_at: '2024-01-15 11:00',
    assigned_to: 'Alex Chen',
    resolved_by: 'Alex Chen',
    status: 'Closed',
    priority: 'High',
    category: 'Technical',
    resolution_time_hours: 1.8,
    customer_name: 'Gamma Ltd',
    subject: 'API timeout issue'
  },
  {
    ticket_id: 'TK-004',
    created_at: '2024-01-15 14:30',
    assigned_to: 'Marcus Johnson',
    resolved_by: 'Marcus Johnson',
    status: 'Closed',
    priority: 'Low',
    category: 'General',
    resolution_time_hours: 6.5,
    customer_name: 'Delta Co',
    subject: 'Feature request'
  },
  {
    ticket_id: 'TK-005',
    created_at: '2024-01-15 15:45',
    assigned_to: 'Priya Sharma',
    resolved_by: 'Priya Sharma',
    status: 'Closed',
    priority: 'High',
    category: 'Account',
    resolution_time_hours: 3.2,
    customer_name: 'Epsilon Corp',
    subject: 'Payment method declined'
  },
  {
    ticket_id: 'TK-006',
    created_at: '2024-01-16 08:00',
    assigned_to: 'Alex Chen',
    resolved_by: 'Alex Chen',
    status: 'Closed',
    priority: 'Medium',
    category: 'Technical',
    resolution_time_hours: 2.1,
    customer_name: 'Zeta Systems',
    subject: 'Dashboard loading slow'
  },
  {
    ticket_id: 'TK-007',
    created_at: '2024-01-16 09:30',
    assigned_to: 'Sarah Williams',
    resolved_by: 'Sarah Williams',
    status: 'Closed',
    priority: 'High',
    category: 'Billing',
    resolution_time_hours: 5.5,
    customer_name: 'Eta Industries',
    subject: 'Multiple charges'
  },
  {
    ticket_id: 'TK-008',
    created_at: '2024-01-16 11:00',
    assigned_to: 'Marcus Johnson',
    resolved_by: 'Marcus Johnson',
    status: 'Closed',
    priority: 'Low',
    category: 'General',
    resolution_time_hours: 7.2,
    customer_name: 'Theta Corp',
    subject: 'Documentation question'
  }
];

const DEMO_PREVIEW: PreviewTable = {
  sheet: 'Tickets',
  shape: [12, 10],
  columns: [
    {
      name: 'ticket_id',
      dtype: 'string',
      non_null: 12,
      nulls: 0,
      sample: ['TK-001', 'TK-006', 'TK-012']
    },
    {
      name: 'priority',
      dtype: 'string',
      non_null: 12,
      nulls: 0,
      sample: ['High', 'Medium', 'Low']
    },
    {
      name: 'resolution_time_hours',
      dtype: 'float',
      non_null: 12,
      nulls: 0,
      sample: ['1.8', '3.2', '7.2']
    },
    {
      name: 'category',
      dtype: 'string',
      non_null: 12,
      nulls: 0,
      sample: ['Account', 'Billing', 'Technical']
    }
  ],
  rows: DEMO_ROWS,
  cached: true,
  sha16: 'demo',
  sheet_names: ['Tickets']
};

const DEMO_SUMMARY: IndexExcelResponse['summary'] = {
  text: 'Support tickets across account, billing, and technical categories.',
  columns: [
    { name: 'priority', dtype: 'string', top_values: [['High', 6], ['Medium', 4], ['Low', 2]], stats: null },
    { name: 'category', dtype: 'string', top_values: [['Account', 4], ['Billing', 3], ['Technical', 3]], stats: null },
    { name: 'resolution_time_hours', dtype: 'float', top_values: null, stats: { min: 1.8, max: 7.2 } }
  ],
  metrics: [
    {
      column: 'priority',
      description: 'Tickets by priority',
      values: [
        { label: 'High', count: 6 },
        { label: 'Medium', count: 4 },
        { label: 'Low', count: 2 }
      ]
    }
  ],
  insights: {
    priority: [
      { label: 'High priority dominant', count: 6 }
    ],
    category: [
      { label: 'Account + Billing heavy', count: 7 }
    ]
  },
  aggregates: [],
  relationships: {},
  analysis_plan: [],
  tags: ['SLA risk', 'High priority', 'Billing', 'Account', 'Technical', 'Resolution time']
};

const DEMO_PROFILE_BASE = {
  indexed_chunks: 128,
  rows: 12,
  sheet: 'Tickets',
  sha16: 'demo',
  summary: DEMO_SUMMARY
};

function buildDemoProfile(sourceName: string, chunkSize: number, overlap: number): IndexExcelResponse {
  return {
    ...DEMO_PROFILE_BASE,
    source: sourceName,
    chunk_config: {
      max_chars: chunkSize,
      overlap
    }
  };
}

export default function UploadPanel({ onPreviewed, onProfiled, onFileSelected }: UploadPanelProps) {
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
  const [isDemoFile, setIsDemoFile] = useState(false);
  const [demoUploadProgress, setDemoUploadProgress] = useState<number | null>(null);
  const demoIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const demoTimeoutRef = useRef<NodeJS.Timeout | null>(null);

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
    if (demoIntervalRef.current) {
      clearInterval(demoIntervalRef.current);
      demoIntervalRef.current = null;
    }
    if (demoTimeoutRef.current) {
      clearTimeout(demoTimeoutRef.current);
      demoTimeoutRef.current = null;
    }
    setDemoUploadProgress(null);
    setFile(nextFile);
    onFileSelected?.(nextFile);
    setIsDemoFile(Boolean(nextFile?.name?.startsWith('demo-support-tickets')));
    setSheet('');
    setSheetOptions([]);
    setLastPreview(null);
    setLastProfile(null);
    setStatus(nextFile ? `Ready to preview ${nextFile.name}` : 'Pick a workbook to start.');
    onPreviewed?.(null);
    onProfiled?.(null, null);
  }

  function runDemoUpload(nextFile: File | null) {
    if (!nextFile) {
      processFile(null);
      return;
    }
    if (demoIntervalRef.current) clearInterval(demoIntervalRef.current);
    if (demoTimeoutRef.current) clearTimeout(demoTimeoutRef.current);
    setIsDragActive(true);
    setDemoUploadProgress(0);
    setStatus(`Uploading ${nextFile.name}…`);
    let progress = 0;
    demoIntervalRef.current = setInterval(() => {
      progress = Math.min(100, progress + 12 + Math.round(Math.random() * 8));
      setDemoUploadProgress(progress);
      if (progress >= 100) {
        if (demoIntervalRef.current) {
          clearInterval(demoIntervalRef.current);
          demoIntervalRef.current = null;
        }
        setIsDragActive(false);
        demoTimeoutRef.current = setTimeout(() => {
          processFile(nextFile);
        }, 200);
      }
    }, 120);
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
      if (isDemoFile) {
        setLastPreview(DEMO_PREVIEW);
        onPreviewed?.(DEMO_PREVIEW);
        setSheet(DEMO_PREVIEW.sheet);
        setSheetOptions(DEMO_PREVIEW.sheet_names ?? []);
        setStatus(`Previewing ${DEMO_PREVIEW.sheet} · ${DEMO_PREVIEW.shape[0].toLocaleString()} rows`);
      } else {
        setStatus(err instanceof Error ? err.message : 'Preview failed');
      }
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
      if (isDemoFile) {
        const sourceName = file?.name || 'demo-support-tickets.xlsx';
        const demoProfile = buildDemoProfile(sourceName, chunkSize, overlap);
        setLastProfile(demoProfile);
        const canonicalSource = demoProfile.sheet ? `${demoProfile.source}:${demoProfile.sheet}` : demoProfile.source;
        setStatus(`✓ Indexed ${canonicalSource}. Context ready.`);
        onProfiled?.(canonicalSource || null, demoProfile);
      } else {
        setStatus(err instanceof Error ? err.message : 'Index failed');
      }
    } finally {
      setIndexPending(false);
    }
  }

  useEffect(() => {
    const handleDemoUpload = (event: Event) => {
      const customEvent = event as CustomEvent;
      runDemoUpload(customEvent.detail?.file ?? null);
    };

    const handleDemoPreview = () => {
      void handlePreview();
    };

    const handleDemoIndex = () => {
      void handleIndex();
    };

    window.addEventListener('demo:upload-file', handleDemoUpload);
    window.addEventListener('demo:preview-file', handleDemoPreview);
    window.addEventListener('demo:index-file', handleDemoIndex);

    return () => {
      window.removeEventListener('demo:upload-file', handleDemoUpload);
      window.removeEventListener('demo:preview-file', handleDemoPreview);
      window.removeEventListener('demo:index-file', handleDemoIndex);
    };
  }, [handleIndex, handlePreview, processFile]);

  useEffect(() => {
    return () => {
      if (demoIntervalRef.current) clearInterval(demoIntervalRef.current);
      if (demoTimeoutRef.current) clearTimeout(demoTimeoutRef.current);
    };
  }, []);

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
          isDragActive || demoUploadProgress !== null
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

      {demoUploadProgress !== null && (
        <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4">
          <div className="flex items-center justify-between text-xs uppercase tracking-[0.3em] text-amber-200">
            <span>Auto upload</span>
            <span>{demoUploadProgress}%</span>
          </div>
          <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-black/30">
            <div
              className="h-full rounded-full bg-gradient-to-r from-amber-400 via-pink-400 to-sky-400 transition-all"
              style={{ width: `${demoUploadProgress}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-amber-100/70">Streaming demo workbook into Dawn.</p>
        </div>
      )}

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
