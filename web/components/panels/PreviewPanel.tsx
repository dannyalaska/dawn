'use client';

import { PreviewTable } from '@/lib/types';
import clsx from 'clsx';

interface PreviewPanelProps {
  preview: PreviewTable | null;
}

export default function PreviewPanel({ preview }: PreviewPanelProps) {
  if (!preview) {
    return (
      <div className="rounded-3xl border border-dashed border-white/15 p-6 text-sm text-slate-400">
        Preview a workbook to inspect sample rows before indexing.
      </div>
    );
  }

  const sampleRows = preview.rows.slice(0, 8);
  const columns = preview.columns.map((c) => c.name);

  return (
    <div className="overflow-hidden rounded-3xl border border-white/10 bg-white/5">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-6 py-4">
        <div>
          <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Preview</p>
          <h3 className="text-lg font-semibold text-white">
            {preview.sheet} · {preview.shape[0].toLocaleString()} rows
          </h3>
        </div>
        {preview.sheet_names?.length ? (
          <span className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300">
            {preview.sheet_names.length} sheets detected
          </span>
        ) : null}
      </div>
      <div className="scroll-soft overflow-x-auto">
        <table className="min-w-full divide-y divide-white/10 text-sm text-slate-200">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col} className="bg-white/5 px-4 py-2 text-left text-xs uppercase tracking-[0.3em] text-slate-400">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sampleRows.map((row, idx) => (
              <tr key={idx} className={clsx('border-b border-white/5', idx % 2 === 0 ? 'bg-transparent' : 'bg-white/5')}>
                {columns.map((col) => (
                  <td key={col} className="px-4 py-2 text-xs text-slate-100">
                    {(row[col] ?? '').toString()}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
