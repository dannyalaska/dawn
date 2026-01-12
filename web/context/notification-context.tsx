'use client';

import { useState, useCallback, createContext, useContext } from 'react';
import { ToastContainer, type ToastMessage, type ToastType } from '@/components/ui/Toast';
import Onboarding from '@/components/ui/Onboarding';

interface NotificationContextType {
  addToast: (type: ToastType, title: string, message?: string) => void;
  showOnboarding: () => void;
  hideOnboarding: () => void;
}

const NotificationContext = createContext<NotificationContextType | undefined>(undefined);

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [showOnboardingModal, setShowOnboardingModal] = useState(false);

  const addToast = useCallback((type: ToastType, title: string, message?: string) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const newToast: ToastMessage = {
      id,
      type,
      title,
      message,
      duration: type === 'error' ? 5000 : 4000
    };
    setToasts((prev) => [...prev, newToast]);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showOnboarding = useCallback(() => {
    setShowOnboardingModal(true);
  }, []);

  const hideOnboarding = useCallback(() => {
    setShowOnboardingModal(false);
  }, []);

  return (
    <NotificationContext.Provider value={{ addToast, showOnboarding, hideOnboarding }}>
      {children}
      <ToastContainer toasts={toasts} onClose={removeToast} />
      {showOnboardingModal && <Onboarding onClose={hideOnboarding} />}
    </NotificationContext.Provider>
  );
}

export function useNotification() {
  const context = useContext(NotificationContext);
  if (context === undefined) {
    throw new Error('useNotification must be used within NotificationProvider');
  }
  return context;
}
