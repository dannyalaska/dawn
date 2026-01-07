import Link from 'next/link';
import { SparklesIcon, ArrowUpRightIcon } from '@heroicons/react/24/outline';
import DataAurora from '@/components/charts/DataAurora';

const stats = [
  { label: 'Context notes curated', value: '12.4k' },
  { label: 'Deterministic metrics cached', value: '483' },
  { label: 'Agent swarm uptime', value: '99.7%' }
];

export default function DawnHero() {
  return (
    <section className="relative grid gap-8 lg:grid-cols-2">
      <div className="glass-panel rounded-3xl border border-white/5 p-8 shadow-aurora">
        <div className="inline-flex items-center gap-2 rounded-full border border-white/10 px-3 py-1 text-xs uppercase tracking-[0.2em] text-amber-200/80">
          <SparklesIcon className="h-4 w-4" />
          dawn horizon workspace
        </div>
        <h1 className="mt-6 text-5xl font-semibold leading-tight text-white">
          Bring Dawn's agent swarm to life in a cinematic cockpit.
        </h1>
        <p className="mt-6 text-lg text-slate-300">
          Upload spreadsheets, preview context memory, orchestrate agent plans, and watch real-time telemetry pulse
          through Dawn's new immersive surface. Built with Next.js, WebGL, and plenty of sunrise gradients.
        </p>
        <div className="mt-8 flex flex-wrap gap-4">
          <Link
            href="#ingest"
            className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-amber-400 via-pink-500 to-sky-500 px-6 py-3 font-semibold text-slate-900 shadow-aurora"
          >
            Upload new workbook
            <ArrowUpRightIcon className="h-4 w-4" />
          </Link>
          <Link
            href="https://github.com/dannyalaska/dawn"
            className="inline-flex items-center gap-2 rounded-full border border-white/10 px-6 py-3 font-medium text-slate-200 hover:border-white/30"
          >
            Explore docs
          </Link>
        </div>
        <dl className="mt-10 grid gap-4 text-left sm:grid-cols-3">
          {stats.map((stat) => (
            <div key={stat.label} className="rounded-2xl border border-white/5 bg-white/5 px-4 py-3">
              <dt className="text-xs uppercase tracking-[0.3em] text-slate-400">{stat.label}</dt>
              <dd className="mt-2 text-2xl font-semibold text-white">{stat.value}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div className="glass-panel flex flex-col rounded-3xl border border-white/5 p-6">
        <p className="text-sm uppercase tracking-[0.4em] text-slate-400">Live telemetry</p>
        <h2 className="mt-3 text-2xl font-semibold">Agent orbits &amp; embeddings</h2>
        <p className="mt-2 text-sm text-slate-300">
          Each particle represents a context vector; ribbons show active agent threads.
        </p>
        <div className="mt-4">
          <DataAurora />
        </div>
      </div>
    </section>
  );
}
