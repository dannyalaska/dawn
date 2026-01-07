'use client';

import { useEffect, useRef } from 'react';
import {
  CloudArrowUpIcon,
  SparklesIcon,
  ChatBubbleLeftRightIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  CpuChipIcon,
  DocumentTextIcon
} from '@heroicons/react/24/outline';

export interface ActivityItem {
  id: string;
  type: 'upload' | 'profile' | 'index' | 'agent' | 'chat' | 'success' | 'warning' | 'info';
  message: string;
  timestamp: Date;
  detail?: string;
}

interface ActivityFeedProps {
  activities: ActivityItem[];
  maxItems?: number;
}

const iconMap = {
  upload: CloudArrowUpIcon,
  profile: DocumentTextIcon,
  index: CheckCircleIcon,
  agent: SparklesIcon,
  chat: ChatBubbleLeftRightIcon,
  success: CheckCircleIcon,
  warning: ExclamationTriangleIcon,
  info: CpuChipIcon
};

const colorMap = {
  upload: 'text-sky-400 bg-sky-500/10',
  profile: 'text-amber-400 bg-amber-500/10',
  index: 'text-emerald-400 bg-emerald-500/10',
  agent: 'text-pink-400 bg-pink-500/10',
  chat: 'text-indigo-400 bg-indigo-500/10',
  success: 'text-emerald-400 bg-emerald-500/10',
  warning: 'text-amber-400 bg-amber-500/10',
  info: 'text-slate-400 bg-slate-500/10'
};

function formatTime(date: Date): string {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const seconds = Math.floor(diff / 1000);

  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return date.toLocaleDateString();
}

export default function ActivityFeed({ activities, maxItems = 10 }: ActivityFeedProps) {
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = 0;
    }
  }, [activities.length]);

  const displayActivities = activities.slice(0, maxItems);

  if (displayActivities.length === 0) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/5 p-6">
        <p className="text-xs uppercase tracking-[0.4em] text-slate-500">Activity</p>
        <p className="mt-4 text-center text-sm text-slate-500">
          No activity yet. Upload a workbook to get started.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <p className="mb-4 text-xs uppercase tracking-[0.4em] text-slate-500">Recent Activity</p>
      <div
        ref={feedRef}
        className="max-h-64 space-y-3 overflow-y-auto scroll-soft pr-2"
      >
        {displayActivities.map((activity, index) => {
          const Icon = iconMap[activity.type];
          const colorClass = colorMap[activity.type];

          return (
            <div
              key={activity.id}
              className={`flex gap-3 rounded-xl bg-white/5 p-3 transition-all duration-300 ${
                index === 0 ? 'animate-slide-in' : ''
              }`}
            >
              <div className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg ${colorClass}`}>
                <Icon className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-white">{activity.message}</p>
                {activity.detail && (
                  <p className="mt-0.5 truncate text-xs text-slate-500">{activity.detail}</p>
                )}
              </div>
              <span className="flex-shrink-0 text-xs text-slate-600">{formatTime(activity.timestamp)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
