'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { ArrowRightIcon, LockClosedIcon } from '@heroicons/react/24/outline';
import { login, register } from '@/lib/api';
import { useDawnSession } from '@/context/dawn-session';

interface AuthFormValues {
  email: string;
  password: string;
  full_name?: string;
}

export default function AuthPanel() {
  const { setSession, user, logout, ready, apiBase } = useDawnSession();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [message, setMessage] = useState<string>('');
  const {
    register: registerField,
    handleSubmit,
    reset,
    formState: { isSubmitting }
  } = useForm<AuthFormValues>({
    defaultValues: { email: 'local@dawn.internal' }
  });

  async function onSubmit(values: AuthFormValues) {
    setMessage('');
    try {
      const payload =
        mode === 'login'
          ? await login(values.email, values.password, { apiBase })
          : await register(
              { email: values.email, password: values.password, full_name: values.full_name },
              { apiBase }
            );
      setSession({ token: payload.token, user: payload.user });
      setMessage('Authenticated — welcome back.');
      reset();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Authentication failed');
    }
  }

  if (!ready) {
    return <div className="rounded-3xl border border-white/10 bg-white/5 p-6 text-sm text-slate-400">Booting auth…</div>;
  }

  if (user) {
    return (
      <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
        <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Signed in</p>
        <h3 className="mt-2 text-2xl font-semibold text-white">{user.email}</h3>
        <p className="mt-2 text-sm text-slate-300">Token stored locally for API calls.</p>
        <button
          type="button"
          onClick={() => logout()}
          className="mt-4 inline-flex items-center gap-2 rounded-full border border-white/10 px-4 py-2 text-sm text-slate-200"
        >
          Log out
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Auth</p>
          <h3 className="mt-2 text-2xl font-semibold text-white">
            {mode === 'login' ? 'Sign in to Dawn' : 'Create a Dawn account'}
          </h3>
        </div>
        <button
          type="button"
          className="text-xs uppercase tracking-[0.3em] text-amber-200"
          onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
        >
          {mode === 'login' ? 'Need an account?' : 'Have an account?'}
        </button>
      </div>
      <form onSubmit={handleSubmit(onSubmit)} className="mt-5 space-y-4">
        <label className="block text-sm text-slate-200">
          Email
          <input
            type="email"
            className="mt-1 w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm"
            {...registerField('email', { required: true })}
          />
        </label>
        <label className="block text-sm text-slate-200">
          Password
          <input
            type="password"
            className="mt-1 w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm"
            {...registerField('password', { required: true })}
          />
        </label>
        {mode === 'register' && (
          <label className="block text-sm text-slate-200">
            Name
            <input
              className="mt-1 w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm"
              {...registerField('full_name')}
            />
          </label>
        )}
        <button
          type="submit"
          disabled={isSubmitting}
          className="flex w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-amber-400 via-pink-500 to-sky-500 px-4 py-2 font-semibold text-slate-900 shadow-aurora disabled:opacity-50"
        >
          <LockClosedIcon className="h-4 w-4" />
          {isSubmitting ? 'Sending…' : mode === 'login' ? 'Log in' : 'Register'}
          <ArrowRightIcon className="h-4 w-4" />
        </button>
        {message && <p className="text-sm text-slate-300">{message}</p>}
      </form>
    </div>
  );
}
