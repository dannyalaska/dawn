import { useState, useCallback } from 'react';
import type { ToastMessage, ToastType } from '@/components/ui/Toast';

export function useToast() {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const addToast = useCallback(
    (type: ToastType, title: string, message?: string, duration?: number) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const newToast: ToastMessage = { id, type, title, message, duration };
      setToasts((prev) => [...prev, newToast]);
      return id;
    },
    []
  );

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const success = useCallback(
    (title: string, message?: string) => addToast('success', title, message, 4000),
    [addToast]
  );

  const error = useCallback(
    (title: string, message?: string) => addToast('error', title, message, 5000),
    [addToast]
  );

  const warning = useCallback(
    (title: string, message?: string) => addToast('warning', title, message, 4000),
    [addToast]
  );

  const info = useCallback(
    (title: string, message?: string) => addToast('info', title, message, 4000),
    [addToast]
  );

  return { toasts, addToast, removeToast, success, error, warning, info };
}
