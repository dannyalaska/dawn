'use client';

import { useMemo } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  PieChart,
  Pie,
  Cell
} from 'recharts';
import type { IndexExcelResponse } from '@/lib/types';

const COLORS = ['#fbbf24', '#f472b6', '#38bdf8', '#22c55e', '#c084fc'];

interface ChartsPanelProps {
  summary: IndexExcelResponse['summary'] | null | undefined;
}

export default function ChartsPanel({ summary }: ChartsPanelProps) {
  const metricData = useMemo(() => {
    if (!summary?.metrics?.length) return [];
    const first = summary.metrics[0];
    return (first.values || []).map((v) => ({ name: v.label, value: v.count }));
  }, [summary]);

  const tagData = useMemo(() => {
    if (!summary?.tags?.length) return [];
    return summary.tags.map((tag, idx) => ({ name: tag, value: summary.tags.length - idx }));
  }, [summary]);

  if (!summary) {
    return (
      <div className="rounded-3xl border border-dashed border-white/15 p-6 text-sm text-slate-400">
        Run "Send to Dawn" to unlock automated charts.
      </div>
    );
  }

  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
      <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Auto charts</p>
      <h3 className="mt-1 text-lg font-semibold text-white">Top findings</h3>
      <div className="mt-4 grid gap-6 lg:grid-cols-2">
        <div className="h-64 rounded-2xl border border-white/10 bg-black/30 p-3">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">
            {(summary.metrics?.[0]?.description || summary.metrics?.[0]?.column || 'Metric')}
          </p>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={metricData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="name" stroke="#94a3b8" />
              <YAxis stroke="#94a3b8" />
              <Tooltip contentStyle={{ background: '#0b1124', border: '1px solid #1e293b' }} />
              <Bar dataKey="value" fill="#fbbf24" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="h-64 rounded-2xl border border-white/10 bg-black/30 p-3">
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Tags</p>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={tagData} dataKey="value" nameKey="name" outerRadius={90} innerRadius={40}>
                {tagData.map((entry, index) => (
                  <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ background: '#0b1124', border: '1px solid #1e293b' }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
