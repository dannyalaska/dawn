'use client';

import { useEffect, useState } from 'react';
import { CheckCircleIcon, ExclamationTriangleIcon, XMarkIcon, InformationCircleIcon } from '@heroicons/react/24/outline';
import clsx from 'clsx';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface ToastMessage {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  duration?: number;
}

interface ToastProps {
  toast: ToastMessage;
  onClose: (id: string) => void;
}

const iconMap = {
  success: { Icon: CheckCircleIcon, color: 'text-emerald-400 bg-emerald-500/10' },
  error: { Icon: XMarkIcon, color: 'text-rose-400 bg-rose-500/10' },
  warning: { Icon: ExclamationTriangleIcon, color: 'text-amber-400 bg-amber-500/10' },
  info: { Icon: InformationCircleIcon, color: 'text-sky-400 bg-sky-500/10' }
};

export function Toast({ toast, onClose }: ToastProps) {
  const [isExiting, setIsExiting] = useState(false);
  const { Icon, color } = iconMap[toast.type];

  useEffect(() => {
    const duration = toast.duration || 5000;
    const timer = setTimeout(() => {
      setIsExiting(true);
      setTimeout(() => onClose(toast.id), 300);
    }, duration);

    return () => clearTimeout(timer);
  }, [toast.id, toast.duration, onClose]);

  return (
    <div
      className={clsx(
        'animate-slide-in glass-panel-sm flex gap-3 rounded-2xl p-4 backdrop-blur-md transition-all',
        isExiting && 'animate-fade-out opacity-0'
      )}
    >
      <div className={clsx('flex-shrink-0 rounded-full p-2', color)}>
        <Icon className="h-5 w-5" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-sm text-slate-100">{toast.title}</p>
        {toast.message && <p className="text-sm text-slate-400 mt-1">{toast.message}</p>}
      </div>
      <button
        onClick={() => {
          setIsExiting(true);
          setTimeout(() => onClose(toast.id), 300);
        }}
        className="flex-shrink-0 text-slate-500 hover:text-slate-300 transition-colors"
      >
        <XMarkIcon className="h-5 w-5" />
      </button>
    </div>
  );
}

interface ToastContainerProps {
  toasts: ToastMessage[];
  onClose: (id: string) => void;
}

export function ToastContainer({ toasts, onClose }: ToastContainerProps) {
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-3 max-w-sm pointer-events-none">
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto">
          <Toast toast={toast} onClose={onClose} />
        </div>
      ))}
    </div>
  );
}
