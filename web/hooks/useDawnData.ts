'use client';

import useSWR, { SWRConfiguration, SWRResponse } from 'swr';
import { useDawnSession } from '@/context/dawn-session';

export default function useDawnData<T>(
  key: readonly unknown[] | null,
  fetcher: (ctx: { token: string | null; apiBase: string }) => Promise<T>,
  config?: SWRConfiguration<T>
): SWRResponse<T, Error> {
  const { token, apiBase, ready } = useDawnSession();
  const swrKey = ready && key ? [...key, token, apiBase] : null;
  return useSWR<T>(swrKey, () => fetcher({ token, apiBase }), config);
}
