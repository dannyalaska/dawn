import { useCallback, useEffect, useRef, useState } from 'react';
import { useDawnSession } from '@/context/dawn-session';
import { ingestFeed } from '@/lib/api';

interface DemoStep {
  step: number;
  duration_seconds: number;
  title: string;
  description: string;
  caption: string;
  highlight_element: string;
  tile_id: string | null;
  action: string;
  question?: string;
  demo_answer?: string;
}

interface UseDemoModeReturn {
  isActive: boolean;
  isPlaying: boolean;
  currentStep: number;
  totalSteps: number;
  steps: DemoStep[];
  currentStepData: DemoStep | null;
  startDemo: () => Promise<void>;
  stopDemo: () => void;
}

const DEMO_FEED_IDENTIFIER = 'support_tickets_demo';
const DEMO_FEED_NAME = 'Support Tickets';
const DEMO_SHEET = 'Tickets';

export function useDemoMode(): UseDemoModeReturn {
  const { token, apiBase } = useDawnSession();
  const [isActive, setIsActive] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [steps, setSteps] = useState<DemoStep[]>([]);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const demoHeaders = token ? { Authorization: `Bearer ${token}` } : undefined;

  const loadDemoSteps = useCallback(async () => {
    const response = await fetch(`${apiBase}/demo/tour`, { headers: demoHeaders });
    if (!response.ok) {
      throw new Error(`Failed to load demo steps (${response.status})`);
    }
    const data = await response.json();
    setSteps(data.steps ?? []);
    return data.steps ?? [];
  }, [apiBase, demoHeaders]);

  const ingestDemoFeed = useCallback(
    async (file: File) => {
      const form = new FormData();
      form.append('identifier', DEMO_FEED_IDENTIFIER);
      form.append('name', DEMO_FEED_NAME);
      form.append('source_type', 'upload');
      form.append('sheet', DEMO_SHEET);
      form.append('file', file);
      try {
        await ingestFeed(form, { token, apiBase });
      } catch (error) {
        console.error('Failed to ingest demo feed', error);
      }
    },
    [apiBase, token]
  );

  const executeStepAction = useCallback(
    async (step: DemoStep) => {
      if (step.tile_id) {
        window.dispatchEvent(new CustomEvent('demo:focus-tile', { detail: { tileId: step.tile_id } }));
      }
      switch (step.action) {
        case 'auto-upload': {
          const fileResponse = await fetch(`${apiBase}/demo/file`, { headers: demoHeaders });
          if (!fileResponse.ok) {
            throw new Error(`Failed to load demo file (${fileResponse.status})`);
          }
          const blob = await fileResponse.blob();
          const file = new File([blob], 'demo-support-tickets.xlsx', {
            type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
          });
          window.dispatchEvent(new CustomEvent('demo:upload-file', { detail: { file } }));
          void ingestDemoFeed(file);
          break;
        }
        case 'auto-preview':
          window.dispatchEvent(new CustomEvent('demo:preview-file'));
          break;
        case 'auto-index':
          window.dispatchEvent(new CustomEvent('demo:index-file'));
          break;
        case 'send-question':
          if (step.question) {
            window.dispatchEvent(
              new CustomEvent('demo:chat-question', {
                detail: { question: step.question, demoAnswer: step.demo_answer ?? null }
              })
            );
          }
          break;
        case 'trigger-agent':
          window.dispatchEvent(new CustomEvent('demo:agent-trigger', { detail: { identifier: DEMO_FEED_IDENTIFIER } }));
          break;
        default:
          break;
      }
    },
    [apiBase, demoHeaders, ingestDemoFeed]
  );

  const startDemo = useCallback(async () => {
    try {
      const loaded = await loadDemoSteps();
      if (!loaded.length) {
        return;
      }
      setIsActive(true);
      setIsPlaying(true);
      setCurrentStep(0);
    } catch (error) {
      console.error('Failed to start demo', error);
    }
  }, [loadDemoSteps]);

  const stopDemo = useCallback(() => {
    setIsActive(false);
    setIsPlaying(false);
    setCurrentStep(0);
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    window.dispatchEvent(new CustomEvent('demo:focus-tile', { detail: { tileId: null } }));
  }, []);

  useEffect(() => {
    if (!isActive || !steps.length) return;
    const step = steps[currentStep];
    if (!step) return;
    void executeStepAction(step);
  }, [currentStep, executeStepAction, isActive, steps]);

  useEffect(() => {
    if (!isActive || !isPlaying || !steps.length) return;
    const step = steps[currentStep];
    if (!step) return;
    timerRef.current = setTimeout(() => {
      if (currentStep < steps.length - 1) {
        setCurrentStep((prev) => prev + 1);
      } else {
        stopDemo();
      }
    }, step.duration_seconds * 1000);
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [currentStep, isActive, isPlaying, steps, stopDemo]);

  return {
    isActive,
    isPlaying,
    currentStep,
    totalSteps: steps.length,
    steps,
    currentStepData: steps[currentStep] ?? null,
    startDemo,
    stopDemo,
  };
}
