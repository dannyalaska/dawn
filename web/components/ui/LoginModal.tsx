'use client';

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useForm } from 'react-hook-form';
import { LockClosedIcon, ArrowRightIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { login, register } from '@/lib/api';
import { useDawnSession } from '@/context/dawn-session';

interface AuthFormValues {
  email: string;
  password: string;
  full_name?: string;
}

const DISMISS_KEY = 'dawn.auth.dismissed';

/**
 * Full-screen modal shown when no session token exists.
 * Dismissed automatically once setSession is called, or by clicking "Skip".
 */
export default function LoginModal() {
  const { token, ready, setSession, apiBase } = useDawnSession();
  const [mounted, setMounted] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [message, setMessage] = useState('');
  const {
    register: registerField,
    handleSubmit,
    reset,
    formState: { isSubmitting }
  } = useForm<AuthFormValues>({
    defaultValues: { email: 'local@dawn.internal' }
  });

  useEffect(() => {
    setMounted(true);
    if (typeof window !== 'undefined' && localStorage.getItem(DISMISS_KEY)) {
      setDismissed(true);
    }
  }, []);

  function dismiss() {
    localStorage.setItem(DISMISS_KEY, '1');
    setDismissed(true);
  }

  // Don't render until hydrated, session is ready, and there's no token
  if (!mounted || !ready || token || dismissed) return null;

  async function onSubmit(values: AuthFormValues) {
    setMessage('');
    try {
      const payload =
        mode === 'login'
          ? await login(values.email, values.password, { apiBase })
          : await register({ email: values.email, password: values.password, full_name: values.full_name }, { apiBase });
      setSession({ token: payload.token, user: payload.user });
      reset();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Authentication failed');
    }
  }

  const modal = (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="relative w-full max-w-sm rounded-3xl border border-white/10 bg-slate-900 p-8 shadow-2xl">
        <button
          type="button"
          aria-label="Dismiss"
          onClick={dismiss}
          className="absolute right-5 top-5 text-slate-500 hover:text-slate-300"
        >
          <XMarkIcon className="h-5 w-5" />
        </button>

        <div className="mb-6 flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Dawn</p>
            <h2 className="mt-1 text-2xl font-semibold text-white">
              {mode === 'login' ? 'Sign in' : 'Create account'}
            </h2>
          </div>
          <button
            type="button"
            aria-label="Switch mode"
            onClick={() => { setMode(m => m === 'login' ? 'register' : 'login'); setMessage(''); }}
            className="text-xs uppercase tracking-[0.3em] text-amber-300 hover:text-amber-200"
          >
            {mode === 'login' ? 'Register' : 'Log in'}
          </button>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <label className="block text-sm text-slate-200">
            Email
            <input
              type="email"
              className="mt-1 w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-cyan-500/50 focus:outline-none"
              {...registerField('email', { required: true })}
            />
          </label>
          <label className="block text-sm text-slate-200">
            Password
            <input
              type="password"
              className="mt-1 w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-cyan-500/50 focus:outline-none"
              {...registerField('password', { required: true })}
            />
          </label>
          {mode === 'register' && (
            <label className="block text-sm text-slate-200">
              Name
              <input
                className="mt-1 w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-cyan-500/50 focus:outline-none"
                {...registerField('full_name')}
              />
            </label>
          )}
          <button
            type="submit"
            disabled={isSubmitting}
            className="flex w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-amber-400 via-pink-500 to-sky-500 px-4 py-2.5 font-semibold text-slate-900 disabled:opacity-50"
          >
            <LockClosedIcon className="h-4 w-4" />
            {isSubmitting ? 'Sending…' : mode === 'login' ? 'Log in' : 'Register'}
            <ArrowRightIcon className="h-4 w-4" />
          </button>
          {message && <p className="text-sm text-rose-300">{message}</p>}
          <button
            type="button"
            onClick={dismiss}
            className="w-full text-center text-xs text-slate-500 hover:text-slate-400"
          >
            Skip for now
          </button>
        </form>
      </div>
    </div>
  );

  return createPortal(modal, document.body);
}
