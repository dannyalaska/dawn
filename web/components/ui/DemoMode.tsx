'use client';

import { useEffect, useRef, useState } from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';

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
}

interface DemoModeOverlayProps {
  isVisible: boolean;
  currentStep: number;
  totalSteps: number;
  step: DemoStep | null;
  onClose: () => void;
}

export function DemoModeOverlay({
  isVisible,
  currentStep,
  totalSteps,
  step,
  onClose
}: DemoModeOverlayProps) {
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);
  const [cursorPos, setCursorPos] = useState<{ x: number; y: number } | null>(null);
  const [pulseKey, setPulseKey] = useState(0);
  const rafRef = useRef<number | null>(null);
  const intervalRef = useRef<number | null>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const observedElementRef = useRef<HTMLElement | null>(null);
  const mutationObserverRef = useRef<MutationObserver | null>(null);

  const caption = step?.caption ?? '';
  const title = step?.title ?? '';
  const description = step?.description ?? '';

  useEffect(() => {
    if (!isVisible || !step) {
      setTargetRect(null);
      return;
    }

    const resolveTarget = () => {
      if (step.highlight_element) {
        const primary = document.querySelector(step.highlight_element);
        if (primary instanceof HTMLElement) {
          return primary;
        }
      }
      if (step.tile_id) {
        const expanded = document.querySelector(`[data-tile-expanded='${step.tile_id}']`);
        if (expanded instanceof HTMLElement) {
          return expanded;
        }
        const fallback = document.querySelector(`[data-demo-target='${step.tile_id}']`);
        if (fallback instanceof HTMLElement) {
          return fallback;
        }
      }
      return null;
    };

    const updateRect = () => {
      const element = resolveTarget();
      if (!element) {
        setTargetRect(null);
        return;
      }
      if (resizeObserverRef.current && observedElementRef.current !== element) {
        resizeObserverRef.current.disconnect();
        resizeObserverRef.current.observe(element);
        observedElementRef.current = element;
      }
      const rect = element.getBoundingClientRect();
      if (rect.width < 40 || rect.height < 40) {
        setTargetRect(null);
        return;
      }
      setTargetRect(rect);
    };

    const scheduleUpdate = () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(updateRect);
    };

    if (typeof ResizeObserver !== 'undefined') {
      resizeObserverRef.current = new ResizeObserver(scheduleUpdate);
    }

    updateRect();
    scheduleUpdate();
    const settleTimers = [200, 600].map((delay) => window.setTimeout(scheduleUpdate, delay));

    window.addEventListener('scroll', scheduleUpdate, true);
    window.addEventListener('resize', scheduleUpdate);
    window.addEventListener('demo:focus-tile', scheduleUpdate);

    mutationObserverRef.current = new MutationObserver(scheduleUpdate);
    mutationObserverRef.current.observe(document.body, {
      attributes: true,
      childList: true,
      subtree: true
    });
    intervalRef.current = window.setInterval(scheduleUpdate, 280);

    return () => {
      window.removeEventListener('scroll', scheduleUpdate, true);
      window.removeEventListener('resize', scheduleUpdate);
      window.removeEventListener('demo:focus-tile', scheduleUpdate);
      settleTimers.forEach((id) => window.clearTimeout(id));
      if (intervalRef.current) {
        window.clearInterval(intervalRef.current);
      }
      if (mutationObserverRef.current) {
        mutationObserverRef.current.disconnect();
      }
      if (resizeObserverRef.current) {
        resizeObserverRef.current.disconnect();
      }
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [isVisible, step]);

  useEffect(() => {
    if (!targetRect) {
      setCursorPos(null);
      return;
    }
    const x = Math.min(targetRect.right - 24, targetRect.left + targetRect.width * 0.7);
    const y = Math.min(targetRect.bottom - 20, targetRect.top + targetRect.height * 0.25);
    setCursorPos({ x, y });
  }, [targetRect]);

  useEffect(() => {
    if (!isVisible) return;
    setPulseKey((prev) => prev + 1);
  }, [currentStep, isVisible]);

  if (!isVisible || !step) return null;

  return (
    <div className="fixed inset-0 z-50 pointer-events-none">
      <div className="absolute inset-0 bg-black/10 pointer-events-auto" onClick={onClose} />

      {targetRect && (
        <div
          className="absolute pointer-events-none transition-[top,left,width,height] duration-500 ease-out"
          style={{
            top: Math.max(targetRect.top - 10, 12),
            left: Math.max(targetRect.left - 10, 12),
            width: targetRect.width + 20,
            height: targetRect.height + 20
          }}
        >
          <div className="absolute -inset-3 rounded-3xl bg-gradient-to-br from-amber-400/20 via-transparent to-sky-400/20 blur-xl" />
          <div className="absolute inset-0 rounded-2xl border border-amber-300 shadow-[0_0_30px_rgba(251,191,36,0.35)]" />
        </div>
      )}

      {cursorPos && (
        <div
          className="absolute pointer-events-none transition-[top,left] duration-500 ease-out"
          style={{
            top: cursorPos.y,
            left: cursorPos.x,
            transform: 'translate(-50%, -50%)'
          }}
        >
          <div
            key={`pulse-${pulseKey}`}
            className="absolute -inset-4 rounded-full bg-amber-300/40 animate-ping"
          />
          <div className="h-3 w-3 rounded-full bg-amber-100 shadow-[0_0_16px_rgba(251,191,36,0.8)] ring-2 ring-white/80" />
        </div>
      )}

      <div className="fixed bottom-6 left-1/2 w-[92vw] max-w-3xl -translate-x-1/2 pointer-events-none">
        <div className="relative rounded-3xl border border-white/10 bg-black/80 px-6 py-5 text-center shadow-2xl">
          <button
            type="button"
            onClick={onClose}
            className="absolute right-4 top-4 rounded-full border border-white/10 bg-black/40 p-2 text-slate-200 pointer-events-auto"
            aria-label="Stop demo"
          >
            <XMarkIcon className="h-4 w-4" />
          </button>
          <p className="text-xs uppercase tracking-[0.35em] text-amber-200">Dawn Demo</p>
          <h3 className="mt-3 text-2xl font-semibold text-white">{title}</h3>
          <p className="mt-2 text-base text-slate-200">{description}</p>
          <p className="mt-3 text-lg font-semibold text-amber-100">{caption}</p>
          <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
            <div
              className="h-full bg-gradient-to-r from-amber-400 via-pink-400 to-sky-400 transition-all duration-300"
              style={{ width: `${((currentStep + 1) / Math.max(totalSteps, 1)) * 100}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
