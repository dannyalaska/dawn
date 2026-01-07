import clsx from 'clsx';
import { HTMLAttributes } from 'react';

interface GlassCardProps extends HTMLAttributes<HTMLDivElement> {
  accent?: 'aurora' | 'ember' | 'plasma';
}

const accentMap: Record<Required<GlassCardProps>['accent'], string> = {
  aurora: 'from-sky-400/40 via-fuchsia-400/30 to-amber-300/40 shadow-aurora',
  ember: 'from-amber-400/40 via-orange-500/30 to-pink-400/40 shadow-ember',
  plasma: 'from-indigo-400/40 via-blue-500/30 to-cyan-400/40 shadow-aurora'
};

export default function GlassCard({
  accent = 'aurora',
  className,
  children,
  ...rest
}: GlassCardProps) {
  return (
    <div
      className={clsx(
        'relative overflow-hidden rounded-3xl border border-white/5 bg-white/5 p-6 text-slate-100 shadow-xl backdrop-blur-2xl transition hover:translate-y-[-2px]',
        className
      )}
      {...rest}
    >
      <div
        className={clsx(
          'pointer-events-none absolute inset-0 rounded-3xl bg-gradient-to-br opacity-20',
          accentMap[accent]
        )}
      />
      <div className="relative z-10">{children}</div>
    </div>
  );
}
