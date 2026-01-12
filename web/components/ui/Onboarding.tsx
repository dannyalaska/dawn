'use client';

import { useCallback, useState } from 'react';
import { SparklesIcon, CheckCircleIcon, ArrowRightIcon, XMarkIcon } from '@heroicons/react/24/outline';
import clsx from 'clsx';

interface OnboardingStep {
  id: string;
  title: string;
  description: string;
  icon: React.ComponentType<any>;
  color: 'amber' | 'sky' | 'pink' | 'emerald';
}

const steps: OnboardingStep[] = [
  {
    id: 'upload',
    title: 'Upload Your Data',
    description: 'Start by uploading an Excel workbook. Dawn will instantly analyze its structure and build a knowledge base.',
    icon: CloudArrowUpIcon,
    color: 'amber'
  },
  {
    id: 'preview',
    title: 'Preview & Index',
    description: 'Review sample rows and customize chunking parameters. Then send to Dawn to vectorize and cache your data.',
    icon: EyeIcon,
    color: 'sky'
  },
  {
    id: 'agents',
    title: 'Run Agent Swarm',
    description: 'Deploy autonomous agents to analyze your data, create metrics, and answer complex questions.',
    icon: SparklesIcon,
    color: 'pink'
  },
  {
    id: 'chat',
    title: 'Chat with Your Data',
    description: 'Ask natural language questions and get answers grounded in your actual data with source citations.',
    icon: ChatBubbleLeftRightIcon,
    color: 'emerald'
  }
];

const colorMap = {
  amber: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  sky: 'bg-sky-500/10 text-sky-400 border-sky-500/20',
  pink: 'bg-pink-500/10 text-pink-400 border-pink-500/20',
  emerald: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
};

import { CloudArrowUpIcon, EyeIcon, ChatBubbleLeftRightIcon } from '@heroicons/react/24/outline';

interface OnboardingProps {
  onClose?: () => void;
}

export default function Onboarding({ onClose }: OnboardingProps) {
  const [currentStep, setCurrentStep] = useState(0);
  const [dismissed, setDismissed] = useState(false);

  const handleNext = useCallback(() => {
    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      setDismissed(true);
      onClose?.();
    }
  }, [currentStep, onClose]);

  const handleSkip = useCallback(() => {
    setDismissed(true);
    onClose?.();
  }, [onClose]);

  if (dismissed) return null;

  const step = steps[currentStep];
  const progress = ((currentStep + 1) / steps.length) * 100;
  const Icon = step.icon;

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 flex items-center justify-center p-4">
      <div className="glass-panel rounded-3xl max-w-md w-full p-6 space-y-6 animate-slide-up">
        {/* Close button */}
        <button
          onClick={handleSkip}
          className="absolute top-4 right-4 text-slate-400 hover:text-slate-200 transition-colors"
        >
          <XMarkIcon className="h-5 w-5" />
        </button>

        {/* Progress bar */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-xs uppercase tracking-[0.3em] text-slate-500">
              Step {currentStep + 1} of {steps.length}
            </p>
            <p className="text-xs text-slate-500">{Math.round(progress)}%</p>
          </div>
          <div className="h-1 bg-white/5 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-amber-400 via-pink-500 to-sky-500 transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Content */}
        <div className="text-center space-y-4">
          <div className={clsx('w-14 h-14 rounded-full mx-auto flex items-center justify-center border', colorMap[step.color])}>
            <Icon className="h-7 w-7" />
          </div>
          <div>
            <h3 className="text-2xl font-bold text-white">{step.title}</h3>
            <p className="text-slate-400 mt-2">{step.description}</p>
          </div>
        </div>

        {/* Step indicators */}
        <div className="flex gap-2 justify-center">
          {steps.map((_, idx) => (
            <button
              key={idx}
              onClick={() => setCurrentStep(idx)}
              className={clsx(
                'h-2 rounded-full transition-all',
                idx === currentStep
                  ? 'bg-amber-400 w-6'
                  : idx < currentStep
                  ? 'bg-emerald-500 w-2'
                  : 'bg-slate-700 w-2'
              )}
            />
          ))}
        </div>

        {/* Actions */}
        <div className="flex gap-3">
          <button
            onClick={handleSkip}
            className="flex-1 rounded-full border border-white/10 hover:bg-white/5 px-4 py-2 text-sm font-medium text-slate-300 transition-colors"
          >
            Skip
          </button>
          <button
            onClick={handleNext}
            className="flex-1 rounded-full bg-gradient-to-r from-amber-400 via-pink-500 to-sky-500 px-4 py-2 text-sm font-semibold text-white hover:shadow-lg shadow-amber-500/25 transition-all flex items-center justify-center gap-2"
          >
            {currentStep === steps.length - 1 ? (
              <>
                <CheckCircleIcon className="h-4 w-4" />
                Get Started
              </>
            ) : (
              <>
                Next
                <ArrowRightIcon className="h-4 w-4" />
              </>
            )}
          </button>
        </div>

      </div>
    </div>
  );
}
