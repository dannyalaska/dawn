'use client';

import { useState } from 'react';
import AuthPanel from '@/components/panels/AuthPanel';
import ServiceStatusPanel from '@/components/panels/ServiceStatusPanel';
import RunnerMiniPanel from '@/components/panels/RunnerMiniPanel';
import BackendPanel from '@/components/panels/BackendPanel';
import Link from 'next/link';
import Image from 'next/image';
import { ChevronDownIcon } from '@heroicons/react/24/outline';

export default function DawnSidebar() {
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    auth: true,
    system: true,
    jobs: false,
    backend: false
  });

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  return (
    <aside className="w-full max-w-sm space-y-4 lg:sticky lg:top-8">
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

      {/* Collapsible Sections */}
      <div className="space-y-3">
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
