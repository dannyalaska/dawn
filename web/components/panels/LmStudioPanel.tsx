'use client';

import { useEffect, useMemo, useState } from 'react';
import { ArrowPathIcon, CpuChipIcon, PowerIcon, RocketLaunchIcon } from '@heroicons/react/24/outline';
import useDawnData from '@/hooks/useDawnData';
import { loadLmStudioModel, fetchLmStudioModels, unloadLmStudioModel, useLmStudioModel } from '@/lib/api';
import { useDawnSession } from '@/context/dawn-session';
import type { LMStudioModel } from '@/lib/types';
import clsx from 'clsx';

const DEFAULT_BASE_URL = 'http://127.0.0.1:1234';

const parseOptionalInt = (value: string) => {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
};

export default function LmStudioPanel() {
  const { token, apiBase } = useDawnSession();
  const [baseUrlInput, setBaseUrlInput] = useState(DEFAULT_BASE_URL);
  const [baseUrl, setBaseUrl] = useState(DEFAULT_BASE_URL);
  const [selectedId, setSelectedId] = useState('');
  const [identifier, setIdentifier] = useState('');
  const [contextLength, setContextLength] = useState('');
  const [gpuSetting, setGpuSetting] = useState('');
  const [ttlSeconds, setTtlSeconds] = useState('');
  const [unloadOthers, setUnloadOthers] = useState(true);
  const [actionMessage, setActionMessage] = useState('');
  const [actionError, setActionError] = useState(false);
  const [restartHint, setRestartHint] = useState(false);
  const [working, setWorking] = useState<string | null>(null);

  const { data, error, isLoading, mutate } = useDawnData(
    baseUrl ? ['lmstudio-models', baseUrl] : null,
    ({ token, apiBase }) => fetchLmStudioModels({ token, apiBase, baseUrl })
  );

  const models = data?.models ?? [];
  const cliAvailable = data?.cli_available ?? true;

  const loadedModels = useMemo(
    () => models.filter((model) => model.state === 'loaded'),
    [models]
  );

  useEffect(() => {
    if (!models.length) return;
    if (selectedId && models.some((model) => model.id === selectedId)) return;
    const fallback = loadedModels[0] ?? models[0];
    if (fallback?.id) {
      setSelectedId(fallback.id);
    }
  }, [loadedModels, models, selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    setIdentifier(selectedId);
  }, [selectedId]);

  const selectedModel = useMemo<LMStudioModel | undefined>(
    () => models.find((model) => model.id === selectedId),
    [models, selectedId]
  );

  const modelKey = selectedModel?.model_key || selectedId;
  const isLoaded = selectedModel?.state === 'loaded';
  const hasModels = models.length > 0;

  const handleRefresh = () => {
    const nextBase = baseUrlInput.trim() || DEFAULT_BASE_URL;
    if (nextBase !== baseUrl) {
      setBaseUrl(nextBase);
      return;
    }
    mutate();
  };

  const runAction = async (label: string, fn: () => Promise<void>, restartNotice = false) => {
    setWorking(label);
    setActionMessage('');
    setActionError(false);
    setRestartHint(restartNotice);
    try {
      await fn();
      setActionMessage(`${label} complete.`);
      mutate();
    } catch (err) {
      setActionError(true);
      setActionMessage(err instanceof Error ? err.message : `${label} failed.`);
    } finally {
      setWorking(null);
    }
  };

  const handleLoad = () =>
    runAction('Load', async () => {
      if (!modelKey) throw new Error('Select a model to load.');
      await loadLmStudioModel(
        {
          model_key: modelKey,
          base_url: baseUrl,
          identifier: identifier.trim() || undefined,
          context_length: parseOptionalInt(contextLength),
          gpu: gpuSetting.trim() || undefined,
          ttl_seconds: parseOptionalInt(ttlSeconds)
        },
        { token, apiBase }
      );
    });

  const handleEject = () =>
    runAction('Eject', async () => {
      if (!modelKey) throw new Error('Select a model to eject.');
      await unloadLmStudioModel(
        {
          model_key: modelKey,
          base_url: baseUrl
        },
        { token, apiBase }
      );
    });

  const handleEjectAll = () =>
    runAction('Eject all', async () => {
      await unloadLmStudioModel(
        {
          unload_all: true,
          base_url: baseUrl
        },
        { token, apiBase }
      );
    });

  const handleSwap = () =>
    runAction('Swap', async () => {
      if (!modelKey) throw new Error('Select a model to swap to.');
      if (unloadOthers) {
        await unloadLmStudioModel(
          {
            unload_all: true,
            base_url: baseUrl
          },
          { token, apiBase }
        );
      }
      const apiModelName = identifier.trim() || selectedId;
      await loadLmStudioModel(
        {
          model_key: modelKey,
          base_url: baseUrl,
          identifier: apiModelName,
          context_length: parseOptionalInt(contextLength),
          gpu: gpuSetting.trim() || undefined,
          ttl_seconds: parseOptionalInt(ttlSeconds)
        },
        { token, apiBase }
      );
      await useLmStudioModel(
        {
          model: apiModelName,
          base_url: baseUrl,
          provider: 'lmstudio'
        },
        { token, apiBase }
      );
    }, true);

  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-slate-400">LM Studio</p>
          <h3 className="mt-1 text-lg font-semibold text-white">Model manager</h3>
        </div>
        <CpuChipIcon className="h-5 w-5 text-slate-200" />
      </div>
      <p className="mt-2 text-xs text-slate-400">
        Requires the LM Studio server + CLI. Start with <span className="text-slate-200">lms server start</span>.
      </p>

      <label className="mt-4 block text-[11px] uppercase tracking-[0.3em] text-slate-400">
        Base URL
      </label>
      <div className="mt-2 flex flex-col gap-2 sm:flex-row">
        <input
          className="min-w-0 flex-1 rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-slate-200"
          value={baseUrlInput}
          onChange={(event) => setBaseUrlInput(event.target.value)}
          placeholder={DEFAULT_BASE_URL}
        />
        <button
          type="button"
          onClick={handleRefresh}
          className="inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-white/10 px-3 py-2 text-xs uppercase tracking-[0.3em] text-amber-200 sm:w-auto"
        >
          <ArrowPathIcon className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {isLoading && <p className="mt-3 text-sm text-slate-400">Loading LM Studio models…</p>}
      {error && <p className="mt-3 text-sm text-rose-300">{error.message}</p>}
      {!cliAvailable && (
        <p className="mt-3 text-sm text-rose-300">LM Studio CLI not detected. Install `lms` to load models.</p>
      )}

      {hasModels && (
        <>
          <div className="mt-4 flex items-center justify-between text-xs text-slate-400">
            <span>{models.length} models found</span>
            <span>{loadedModels.length} loaded</span>
          </div>

          <label className="mt-3 block text-[11px] uppercase tracking-[0.3em] text-slate-400">
            Model
          </label>
          <select
            className="mt-2 w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-slate-200"
            value={selectedId}
            onChange={(event) => setSelectedId(event.target.value)}
          >
            {models.map((model) => (
              <option key={model.id} value={model.id}>
                {model.display_name || model.id}
              </option>
            ))}
          </select>
          {selectedModel && (
            <div className="mt-2 flex items-center justify-between text-xs text-slate-400">
              <span className="truncate">CLI key: {modelKey || 'n/a'}</span>
              <span className={clsx('rounded-full px-2 py-0.5', isLoaded ? 'bg-emerald-500/20 text-emerald-300' : 'bg-white/10 text-slate-300')}>
                {isLoaded ? 'Loaded' : 'Idle'}
              </span>
            </div>
          )}

          <details className="mt-3 rounded-2xl border border-white/10 bg-black/30 px-3 py-2">
            <summary className="cursor-pointer text-xs uppercase tracking-[0.3em] text-slate-300">
              Advanced load options
            </summary>
            <div className="mt-3 space-y-2 text-sm">
              <label className="block text-xs text-slate-300">
                Identifier
                <input
                  className="mt-1 w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-slate-200"
                  value={identifier}
                  onChange={(event) => setIdentifier(event.target.value)}
                />
              </label>
              <div className="grid gap-2 sm:grid-cols-2">
                <label className="block text-xs text-slate-300">
                  Context length
                  <input
                    type="number"
                    min={0}
                    className="mt-1 w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-slate-200"
                    value={contextLength}
                    onChange={(event) => setContextLength(event.target.value)}
                  />
                </label>
                <label className="block text-xs text-slate-300">
                  Unload after (sec)
                  <input
                    type="number"
                    min={0}
                    className="mt-1 w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-slate-200"
                    value={ttlSeconds}
                    onChange={(event) => setTtlSeconds(event.target.value)}
                  />
                </label>
              </div>
              <label className="block text-xs text-slate-300">
                GPU setting
                <input
                  className="mt-1 w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-slate-200"
                  value={gpuSetting}
                  onChange={(event) => setGpuSetting(event.target.value)}
                  placeholder="auto / max / preset"
                />
              </label>
            </div>
          </details>

          <label className="mt-3 flex items-center gap-2 text-xs text-slate-300">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-white/10 bg-black/40 text-amber-400"
              checked={unloadOthers}
              onChange={(event) => setUnloadOthers(event.target.checked)}
            />
            Unload other models before swap
          </label>

          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            <button
              type="button"
              onClick={handleLoad}
              disabled={!hasModels || !cliAvailable || working !== null}
              className="inline-flex items-center justify-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-xs uppercase tracking-[0.3em] text-slate-200 disabled:opacity-50"
            >
              <RocketLaunchIcon className="h-4 w-4" />
              {working === 'Load' ? 'Loading…' : 'Load'}
            </button>
            <button
              type="button"
              onClick={handleEject}
              disabled={!hasModels || !cliAvailable || working !== null || !isLoaded}
              className="inline-flex items-center justify-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-xs uppercase tracking-[0.3em] text-slate-200 disabled:opacity-50"
            >
              <PowerIcon className="h-4 w-4" />
              {working === 'Eject' ? 'Ejecting…' : 'Eject'}
            </button>
            <button
              type="button"
              onClick={handleEjectAll}
              disabled={!cliAvailable || working !== null}
              className="inline-flex items-center justify-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-xs uppercase tracking-[0.3em] text-slate-200 disabled:opacity-50"
            >
              <PowerIcon className="h-4 w-4" />
              {working === 'Eject all' ? 'Ejecting…' : 'Eject all'}
            </button>
            <button
              type="button"
              onClick={handleSwap}
              disabled={!hasModels || !cliAvailable || working !== null}
              className="inline-flex items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-amber-400 via-pink-500 to-sky-500 px-3 py-2 text-xs font-semibold text-slate-900 shadow-aurora disabled:opacity-50"
            >
              <RocketLaunchIcon className="h-4 w-4" />
              {working === 'Swap' ? 'Swapping…' : 'Swap + use'}
            </button>
          </div>
        </>
      )}

      {!isLoading && !hasModels && !error && (
        <p className="mt-4 text-sm text-slate-400">No models returned. Make sure LM Studio is running.</p>
      )}

      {actionMessage && (
        <p className={clsx('mt-3 text-xs', actionError ? 'text-rose-300' : 'text-emerald-300')}>
          {actionMessage} {actionError || !restartHint ? '' : 'Restart backend to apply model changes.'}
        </p>
      )}
    </div>
  );
}
