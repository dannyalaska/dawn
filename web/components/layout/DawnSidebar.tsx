'use client';

import { useState } from 'react';
import AuthPanel from '@/components/panels/AuthPanel';
import ServiceStatusPanel from '@/components/panels/ServiceStatusPanel';
import RunnerMiniPanel from '@/components/panels/RunnerMiniPanel';
import BackendPanel from '@/components/panels/BackendPanel';
import LmStudioPanel from '@/components/panels/LmStudioPanel';
import ModelProviderPanel from '@/components/panels/ModelProviderPanel';
import Link from 'next/link';
import Image from 'next/image';
import { ChevronDownIcon, PlayIcon } from '@heroicons/react/24/outline';
import { useDawnSession } from '@/context/dawn-session';
import { seedDemo } from '@/lib/api';

export default function DawnSidebar() {
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    lmstudio: true,
    auth: true,
    system: true,
    jobs: false,
    backend: false
  });
  const [demoSeeding, setDemoSeeding] = useState(false);
  const [demoMessage, setDemoMessage] = useState<string | null>(null);
  const { token, apiBase } = useDawnSession();

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  async function handleRunDemo() {
    setDemoSeeding(true);
    setDemoMessage(null);
    try {
      const result = await seedDemo({ token, apiBase });
      const count = result.feeds?.length ?? 0;
      setDemoMessage(result.ok ? `✓ Seeded ${count} feed${count !== 1 ? 's' : ''}` : `Partial: ${result.errors?.join(', ')}`);
      window.dispatchEvent(new Event('workspace:reset'));
    } catch (err) {
      setDemoMessage(err instanceof Error ? err.message : 'Demo seed failed');
    } finally {
      setDemoSeeding(false);
    }
  }

  return (
    <aside className="w-full max-w-sm space-y-4 lg:sticky lg:top-8" data-demo-target="dawn-sidebar">
      {/* Logo & Branding */}
      <Link
        href="/"
        className="flex items-center gap-3 glass-panel rounded-3xl px-5 py-4 text-lg font-semibold text-white hover:bg-white/10 transition-colors"
      >
        <Image
          src="/dawn_logo.png"
          alt="Dawn"
          width={40}
          height={40}
          className="h-10 w-10 rounded-full object-contain"
        />
        <span>Dawn</span>
      </Link>

      {/* Run Demo */}
      <div className="glass-panel rounded-2xl p-4 space-y-2">
        <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Quick start</p>
        <button
          type="button"
          onClick={handleRunDemo}
          disabled={demoSeeding}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-cyan-500 to-violet-500 px-4 py-2.5 text-sm font-semibold text-slate-900 disabled:opacity-50 transition hover:opacity-90"
        >
          <PlayIcon className="h-4 w-4" />
          {demoSeeding ? 'Seeding workspace…' : 'Run Demo'}
        </button>
        {demoMessage && (
          <p className={`text-xs ${demoMessage.startsWith('✓') ? 'text-emerald-400' : 'text-rose-400'}`}>
            {demoMessage}
          </p>
        )}
      </div>

      {/* Collapsible Sections */}
      <div className="space-y-3">
        {/* Model Provider */}
        <div className="glass-panel rounded-2xl p-4 space-y-3">
          <button
            onClick={() => toggleSection('lmstudio')}
            className="flex items-center justify-between w-full text-xs uppercase tracking-[0.3em] font-semibold text-slate-400 hover:text-slate-300 transition-colors"
          >
            <span>Model Provider</span>
            <ChevronDownIcon
              className={`h-4 w-4 transition-transform ${expandedSections.lmstudio ? 'rotate-180' : ''}`}
            />
          </button>
          {expandedSections.lmstudio && (
            <div className="space-y-4">
              <ModelProviderPanel />
              <details className="rounded-2xl border border-white/8 bg-white/3">
                <summary className="cursor-pointer px-3 py-2 text-[10px] uppercase tracking-[0.3em] text-slate-500">
                  LM Studio model manager
                </summary>
                <div className="px-1 pb-2 pt-0">
                  <LmStudioPanel />
                </div>
              </details>
            </div>
          )}
        </div>

        {/* Authentication */}
        <div className="glass-panel rounded-2xl p-4 space-y-3">
          <button
            onClick={() => toggleSection('auth')}
            className="flex items-center justify-between w-full text-xs uppercase tracking-[0.3em] font-semibold text-slate-400 hover:text-slate-300 transition-colors"
          >
            <span>Authentication</span>
            <ChevronDownIcon
              className={`h-4 w-4 transition-transform ${expandedSections.auth ? 'rotate-180' : ''}`}
            />
          </button>
          {expandedSections.auth && (
            <div>
              <AuthPanel />
            </div>
          )}
        </div>

        {/* System Status */}
        <div className="glass-panel rounded-2xl p-4 space-y-3">
          <button
            onClick={() => toggleSection('system')}
            className="flex items-center justify-between w-full text-xs uppercase tracking-[0.3em] font-semibold text-slate-400 hover:text-slate-300 transition-colors"
          >
            <span>System Status</span>
            <ChevronDownIcon
              className={`h-4 w-4 transition-transform ${expandedSections.system ? 'rotate-180' : ''}`}
            />
          </button>
          {expandedSections.system && (
            <div>
              <ServiceStatusPanel />
            </div>
          )}
        </div>

        {/* Jobs & Runner */}
        <div className="glass-panel rounded-2xl p-4 space-y-3">
          <button
            onClick={() => toggleSection('jobs')}
            className="flex items-center justify-between w-full text-xs uppercase tracking-[0.3em] font-semibold text-slate-400 hover:text-slate-300 transition-colors"
          >
            <span>Background Jobs</span>
            <ChevronDownIcon
              className={`h-4 w-4 transition-transform ${expandedSections.jobs ? 'rotate-180' : ''}`}
            />
          </button>
          {expandedSections.jobs && (
            <div>
              <RunnerMiniPanel />
            </div>
          )}
        </div>

        {/* Backend Connections */}
        <div className="glass-panel rounded-2xl p-4 space-y-3">
          <button
            onClick={() => toggleSection('backend')}
            className="flex items-center justify-between w-full text-xs uppercase tracking-[0.3em] font-semibold text-slate-400 hover:text-slate-300 transition-colors"
          >
            <span>Backends</span>
            <ChevronDownIcon
              className={`h-4 w-4 transition-transform ${expandedSections.backend ? 'rotate-180' : ''}`}
            />
          </button>
          {expandedSections.backend && (
            <div>
              <BackendPanel />
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
