'use client';

import { CheckCircleIcon, ExclamationTriangleIcon, XCircleIcon, ArrowPathIcon } from '@heroicons/react/24/outline';

export type StatusType = 'idle' | 'loading' | 'success' | 'warning' | 'error';

interface StatusBadgeProps {
  status: StatusType;
  label?: string;
  size?: 'sm' | 'md' | 'lg';
  pulse?: boolean;
}

const statusConfig = {
  idle: {
    icon: null,
    bgClass: 'bg-slate-500/20 border-slate-500/30',
    textClass: 'text-slate-400',
    dotClass: 'bg-slate-400'
  },
  loading: {
    icon: ArrowPathIcon,
    bgClass: 'bg-sky-500/20 border-sky-500/30',
    textClass: 'text-sky-300',
    dotClass: 'bg-sky-400'
  },
  success: {
    icon: CheckCircleIcon,
    bgClass: 'bg-emerald-500/20 border-emerald-500/30',
    textClass: 'text-emerald-300',
    dotClass: 'bg-emerald-400'
  },
  warning: {
    icon: ExclamationTriangleIcon,
    bgClass: 'bg-amber-500/20 border-amber-500/30',
    textClass: 'text-amber-300',
    dotClass: 'bg-amber-400'
  },
  error: {
    icon: XCircleIcon,
    bgClass: 'bg-rose-500/20 border-rose-500/30',
    textClass: 'text-rose-300',
    dotClass: 'bg-rose-400'
  }
};

const sizeConfig = {
  sm: { badge: 'px-2 py-0.5 text-[10px]', icon: 'h-3 w-3', dot: 'h-1.5 w-1.5' },
  md: { badge: 'px-3 py-1 text-xs', icon: 'h-4 w-4', dot: 'h-2 w-2' },
  lg: { badge: 'px-4 py-1.5 text-sm', icon: 'h-5 w-5', dot: 'h-2.5 w-2.5' }
};

export default function StatusBadge({ status, label, size = 'md', pulse = false }: StatusBadgeProps) {
  const config = statusConfig[status];
  const sizing = sizeConfig[size];
  const Icon = config.icon;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-medium uppercase tracking-wider ${config.bgClass} ${config.textClass} ${sizing.badge}`}
    >
      {Icon ? (
        <Icon className={`${sizing.icon} ${status === 'loading' ? 'animate-spin' : ''}`} />
      ) : (
        <span className={`${sizing.dot} rounded-full ${config.dotClass} ${pulse ? 'animate-pulse' : ''}`} />
      )}
      {label && <span>{label}</span>}
    </span>
  );
}
