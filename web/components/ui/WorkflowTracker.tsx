'use client';

import {
  CloudArrowUpIcon,
  TableCellsIcon,
  SparklesIcon,
  ChatBubbleLeftRightIcon,
  CheckCircleIcon
} from '@heroicons/react/24/outline';
import { CheckCircleIcon as CheckCircleSolidIcon } from '@heroicons/react/24/solid';

export type WorkflowStage = 'upload' | 'preview' | 'index' | 'agents' | 'chat';

interface WorkflowTrackerProps {
  currentStage: WorkflowStage;
  completedStages: WorkflowStage[];
}

const stages: { id: WorkflowStage; label: string; icon: typeof CloudArrowUpIcon }[] = [
  { id: 'upload', label: 'Upload', icon: CloudArrowUpIcon },
  { id: 'preview', label: 'Preview', icon: TableCellsIcon },
  { id: 'index', label: 'Index', icon: CheckCircleIcon },
  { id: 'agents', label: 'Agents', icon: SparklesIcon },
  { id: 'chat', label: 'Chat', icon: ChatBubbleLeftRightIcon }
];

export default function WorkflowTracker({ currentStage, completedStages }: WorkflowTrackerProps) {
  const currentIndex = stages.findIndex((s) => s.id === currentStage);

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <div className="flex items-center justify-between">
        {stages.map((stage, index) => {
          const isCompleted = completedStages.includes(stage.id);
          const isCurrent = stage.id === currentStage;
          const isPast = index < currentIndex;
          const Icon = stage.icon;

          return (
            <div key={stage.id} className="flex items-center">
              {/* Step indicator */}
              <div className="flex flex-col items-center">
                <div
                  className={`relative flex h-10 w-10 items-center justify-center rounded-full transition-all duration-300 ${
                    isCompleted
                      ? 'bg-emerald-500 text-white'
                      : isCurrent
                      ? 'bg-amber-500/20 text-amber-400 ring-2 ring-amber-500/50'
                      : 'bg-slate-800 text-slate-500'
                  }`}
                >
                  {isCompleted ? (
                    <CheckCircleSolidIcon className="h-5 w-5" />
                  ) : (
                    <Icon className="h-5 w-5" />
                  )}
                  {isCurrent && (
                    <span className="absolute inset-0 animate-ping rounded-full bg-amber-500/30" />
                  )}
                </div>
                <span
                  className={`mt-2 text-xs font-medium ${
                    isCurrent ? 'text-amber-400' : isCompleted ? 'text-emerald-400' : 'text-slate-500'
                  }`}
                >
                  {stage.label}
                </span>
              </div>

              {/* Connector line */}
              {index < stages.length - 1 && (
                <div
                  className={`mx-2 h-0.5 w-8 sm:w-12 md:w-16 transition-colors duration-300 ${
                    isPast || isCompleted ? 'bg-emerald-500' : 'bg-slate-700'
                  }`}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
