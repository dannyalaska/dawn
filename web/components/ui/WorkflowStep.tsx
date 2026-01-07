'use client';

import { ReactNode } from 'react';
import { CheckIcon } from '@heroicons/react/24/solid';

export type StepStatus = 'pending' | 'active' | 'completed';

interface WorkflowStepProps {
  number: number;
  title: string;
  description: string;
  status: StepStatus;
  icon?: ReactNode;
  isLast?: boolean;
}

export default function WorkflowStep({ number, title, description, status, icon, isLast = false }: WorkflowStepProps) {
  const isActive = status === 'active';
  const isCompleted = status === 'completed';

  return (
    <div className="flex gap-4">
      {/* Step indicator */}
      <div className="flex flex-col items-center">
        <div
          className={`relative flex h-10 w-10 items-center justify-center rounded-full border-2 transition-all duration-500 ${
            isCompleted
              ? 'border-emerald-500 bg-emerald-500 text-white'
              : isActive
              ? 'border-amber-400 bg-amber-400/20 text-amber-400 shadow-lg shadow-amber-500/30'
              : 'border-slate-600 bg-slate-800 text-slate-500'
          }`}
        >
          {isCompleted ? (
            <CheckIcon className="h-5 w-5" />
          ) : icon ? (
            <span className="h-5 w-5">{icon}</span>
          ) : (
            <span className="text-sm font-bold">{number}</span>
          )}
          {isActive && (
            <span className="absolute inset-0 animate-ping rounded-full border-2 border-amber-400 opacity-75" />
          )}
        </div>
        {!isLast && (
          <div
            className={`mt-2 h-full w-0.5 transition-colors duration-500 ${
              isCompleted ? 'bg-emerald-500' : 'bg-slate-700'
            }`}
            style={{ minHeight: '2rem' }}
          />
        )}
      </div>

      {/* Step content */}
      <div className={`pb-8 ${isLast ? 'pb-0' : ''}`}>
        <h4
          className={`text-base font-semibold transition-colors ${
            isActive ? 'text-amber-400' : isCompleted ? 'text-emerald-400' : 'text-slate-400'
          }`}
        >
          {title}
        </h4>
        <p className={`mt-1 text-sm ${isActive ? 'text-slate-300' : 'text-slate-500'}`}>
          {description}
        </p>
      </div>
    </div>
  );
}
