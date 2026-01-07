'use client';

import { FormEvent, useState } from 'react';
import { ServerIcon } from '@heroicons/react/24/outline';
import useDawnData from '@/hooks/useDawnData';
import { createBackend, fetchBackends } from '@/lib/api';
import { useDawnSession } from '@/context/dawn-session';
import clsx from 'clsx';

export default function BackendPanel() {
  const { token, apiBase } = useDawnSession();
  const { data, error, isLoading, mutate } = useDawnData(['backends'], ({ token, apiBase }) =>
    fetchBackends({ token, apiBase })
  );
  const [name, setName] = useState('Local Postgres');
  const [kind, setKind] = useState('postgres');
  const [configText, setConfigText] = useState(
    '{"dsn":"postgresql://dawn:password@localhost:5432/dawn"}'
  );
  const [formError, setFormError] = useState('');

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const parsed = JSON.parse(configText || '{}');
      await createBackend({ name: name.trim(), kind, config: parsed }, { token, apiBase });
      setFormError('');
      mutate();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Could not save connection');
    }
  }

  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Backend settings</p>
          <h3 className="mt-1 text-lg font-semibold text-white">Connections</h3>
        </div>
        <ServerIcon className="h-5 w-5 text-slate-300" />
      </div>
      {isLoading && <p className="mt-4 text-sm text-slate-400">Loading connections…</p>}
      {error && <p className="mt-4 text-sm text-rose-400">{error.message}</p>}
      {!isLoading && !error && (
        <ul className="mt-4 space-y-2 text-sm">
          {(data ?? []).slice(0, 4).map((conn) => (
            <li
              key={conn.id}
              className="flex items-center justify-between rounded-2xl border border-white/10 px-3 py-2 text-slate-200"
            >
              <span>
                {conn.name}
                <span className="ml-2 rounded-full bg-white/5 px-2 py-0.5 text-[11px] uppercase tracking-[0.3em] text-slate-400">
                  {conn.kind}
                </span>
              </span>
              <span className={clsx('text-xs', conn.schema_grants?.length ? 'text-emerald-300' : 'text-slate-400')}>
                {conn.schema_grants?.length || 0} grants
              </span>
            </li>
          ))}
          {(data ?? []).length === 0 && (
            <li className="rounded-2xl border border-dashed border-white/10 px-3 py-2 text-slate-400">
              No connections yet.
            </li>
          )}
        </ul>
      )}
      <p className="mt-4 text-xs text-slate-400">Configure credentialed databases for Dawn agents.</p>
      <form className="mt-4 space-y-2 text-sm text-slate-200" onSubmit={handleCreate}>
        <input
          className="w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2"
          placeholder="Connection name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <select
          className="w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2"
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          <option value="postgres">Postgres</option>
          <option value="mysql">MySQL</option>
          <option value="snowflake">Snowflake</option>
          <option value="s3">S3</option>
        </select>
        <textarea
          className="w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-xs"
          rows={3}
          value={configText}
          onChange={(e) => setConfigText(e.target.value)}
        />
        <button
          type="submit"
          className="w-full rounded-full bg-gradient-to-r from-amber-400 via-pink-500 to-sky-500 px-3 py-2 font-semibold text-slate-900"
        >
          Save connection
        </button>
        {formError && <p className="text-rose-300">{formError}</p>}
      </form>
    </div>
  );
}
