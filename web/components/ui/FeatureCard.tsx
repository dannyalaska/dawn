'use client';

import { ReactNode } from 'react';

interface FeatureCardProps {
  icon: ReactNode;
  title: string;
  description: string;
  gradient?: 'amber' | 'sky' | 'pink' | 'emerald';
  badge?: string;
}

const gradientMap = {
  amber: 'from-amber-500/20 via-orange-500/10 to-transparent',
  sky: 'from-sky-500/20 via-blue-500/10 to-transparent',
  pink: 'from-pink-500/20 via-rose-500/10 to-transparent',
  emerald: 'from-emerald-500/20 via-teal-500/10 to-transparent'
};

const iconGlowMap = {
  amber: 'bg-amber-500/10 text-amber-400 shadow-amber-500/20',
  sky: 'bg-sky-500/10 text-sky-400 shadow-sky-500/20',
  pink: 'bg-pink-500/10 text-pink-400 shadow-pink-500/20',
  emerald: 'bg-emerald-500/10 text-emerald-400 shadow-emerald-500/20'
};

export default function FeatureCard({ icon, title, description, gradient = 'amber', badge }: FeatureCardProps) {
  return (
    <div className="group relative overflow-hidden rounded-2xl border border-white/10 bg-white/5 p-6 transition-all duration-300 hover:border-white/20 hover:bg-white/[0.07]">
      {/* Gradient glow */}
      <div className={`absolute -top-12 -right-12 h-32 w-32 rounded-full bg-gradient-to-br ${gradientMap[gradient]} blur-2xl transition-transform duration-500 group-hover:scale-150`} />

      <div className="relative">
        {badge && (
          <span className="absolute -top-1 -right-1 rounded-full bg-gradient-to-r from-amber-400 via-pink-500 to-sky-500 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-900">
            {badge}
          </span>
        )}

        <div className={`inline-flex h-12 w-12 items-center justify-center rounded-xl ${iconGlowMap[gradient]} shadow-lg`}>
          {icon}
        </div>

        <h3 className="mt-4 text-lg font-semibold text-white">{title}</h3>
        <p className="mt-2 text-sm leading-relaxed text-slate-400">{description}</p>
      </div>
    </div>
  );
}
