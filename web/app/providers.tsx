'use client';

import { ReactNode } from 'react';
import { SWRConfig } from 'swr';
import { DawnSessionProvider } from '@/context/dawn-session';
import { NotificationProvider } from '@/context/notification-context';

export default function Providers({ children }: { children: ReactNode }) {
  return (
    <SWRConfig
      value={{
        revalidateOnFocus: false,
        shouldRetryOnError: false
      }}
    >
      <DawnSessionProvider>
        <NotificationProvider>
          {children}
        </NotificationProvider>
      </DawnSessionProvider>
    </SWRConfig>
  );
}
