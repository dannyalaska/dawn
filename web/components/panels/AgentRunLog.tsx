'use client';

import {
  ChatBubbleLeftRightIcon,
  CheckBadgeIcon,
  ClipboardDocumentCheckIcon,
  CpuChipIcon,
  RocketLaunchIcon,
  ShieldCheckIcon,
  SparklesIcon
} from '@heroicons/react/24/outline';
import type { AgentRunLogEntry } from '@/lib/types';

const AGENT_META: Record<
  string,
  { label: string; icon: typeof SparklesIcon; gradient: string }
> = {
  bootstrap: {
    label: 'Bootstrap',
    icon: RocketLaunchIcon,
    gradient: 'from-sky-400/80 via-cyan-400/70 to-emerald-300/70'
  },
  planner: {
    label: 'Planner',
    icon: ClipboardDocumentCheckIcon,
    gradient: 'from-amber-400/80 via-pink-400/70 to-rose-400/70'
  },
  executor: {
    label: 'Executor',
    icon: CpuChipIcon,
    gradient: 'from-indigo-400/80 via-blue-500/70 to-cyan-400/70'
  },
  memory: {
    label: 'Memory',
    icon: SparklesIcon,
    gradient: 'from-emerald-400/80 via-lime-300/70 to-cyan-300/70'
  },
  qa: {
    label: 'QA',
    icon: ChatBubbleLeftRightIcon,
    gradient: 'from-fuchsia-400/80 via-purple-400/70 to-sky-400/70'
  },
  guardrail: {
    label: 'Guardrail',
    icon: ShieldCheckIcon,
    gradient: 'from-orange-400/80 via-amber-400/70 to-rose-400/70'
  },
  responder: {
    label: 'Responder',
    icon: CheckBadgeIcon,
    gradient: 'from-sky-300/80 via-emerald-300/70 to-lime-300/70'
  }
};

function formatValue(value: unknown) {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

interface AgentRunLogProps {
  log: AgentRunLogEntry[];
}

export default function AgentRunLog({ log }: AgentRunLogProps) {
  if (!log?.length) return null;

  return (
    <div className="rounded-3xl border border-white/10 bg-black/40 p-5 shadow-xl shadow-black/30">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Agent timeline</p>
        <span className="text-[11px] text-slate-500">{log.length} events</span>
      </div>
      <ul className="mt-4 space-y-4">
        {log.map((entry, idx) => {
          const agentKey = (entry.agent as string) || (entry.role as string) || 'agent';
          const meta =
            AGENT_META[agentKey] ??
            ({
              label: agentKey,
              icon: SparklesIcon,
              gradient: 'from-slate-300/60 via-slate-500/60 to-slate-700/60'
            } as const);
          const Icon = meta.icon;
          const message = (entry.message as string) || (entry.content as string) || 'Activity recorded.';
          const extras = Object.entries(entry).filter(
            ([key, value]) =>
              !['agent', 'role', 'message', 'content', 'timestamp'].includes(key) &&
              value !== undefined &&
              value !== null
          );

          return (
            <li key={`${agentKey}-${idx}`} className="flex gap-3">
              <div className="flex flex-col items-center">
                <div
                  className={`flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br ${meta.gradient} text-slate-900 shadow-lg shadow-black/40`}
                >
                  <Icon className="h-5 w-5" />
                </div>
                {idx < log.length - 1 ? (
                  <div className="mt-1 h-full w-px flex-1 bg-gradient-to-b from-white/30 via-white/10 to-transparent" />
                ) : null}
              </div>
              <div className="flex-1 rounded-2xl border border-white/10 bg-white/5 p-4 shadow-inner shadow-black/20">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.3em] text-slate-400">{meta.label}</p>
                    <p className="text-sm font-semibold text-white">{message}</p>
                  </div>
                  <span className="text-[11px] text-slate-500">Step {idx + 1}</span>
                </div>
                {extras.length ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {extras.map(([key, value]) => (
                      <span
                        key={`${agentKey}-${key}-${idx}`}
                        className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-black/30 px-3 py-1 text-[11px] text-slate-200"
                      >
                        <span className="text-slate-400">{key}</span>
                        <span className="font-semibold text-white">{formatValue(value)}</span>
                      </span>
                    ))}
                  </div>
                ) : null}
                {entry.timestamp ? (
                  <p className="mt-2 text-[11px] text-slate-500">{entry.timestamp}</p>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
