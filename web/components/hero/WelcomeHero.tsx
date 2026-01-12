'use client';

import { useEffect, useState } from 'react';
import {
  SparklesIcon,
  TableCellsIcon,
  ChatBubbleLeftRightIcon,
  CpuChipIcon,
  ChartBarIcon,
  ArrowRightIcon
} from '@heroicons/react/24/outline';
import FeatureCard from '@/components/ui/FeatureCard';
import AnimatedCounter from '@/components/ui/AnimatedCounter';

interface WelcomeHeroProps {
  onGetStarted?: () => void;
  hasData?: boolean;
}

const features = [
  {
    icon: <TableCellsIcon className="h-6 w-6" />,
    title: 'Smart Data Profiling',
    description: 'Upload Excel workbooks and watch Dawn instantly analyze schemas, detect patterns, and build a knowledge base.',
    gradient: 'amber' as const,
    badge: 'Start here'
  },
  {
    icon: <SparklesIcon className="h-6 w-6" />,
    title: 'AI Agent Swarm',
    description: 'A coordinated team of AI agents plans, executes, and validates analysis with full transparency.',
    gradient: 'sky' as const
  },
  {
    icon: <ChatBubbleLeftRightIcon className="h-6 w-6" />,
    title: 'RAG-Powered Q&A',
    description: 'Ask natural language questions and get answers grounded in your actual data with source citations.',
    gradient: 'pink' as const
  },
  {
    icon: <ChartBarIcon className="h-6 w-6" />,
    title: 'Deterministic Metrics',
    description: 'Get precise, reproducible answers for KPIs—no hallucinations, just verified calculations.',
    gradient: 'emerald' as const
  }
];

const stats = [
  { label: 'AI Agents', value: 4, suffix: '' },
  { label: 'LLM Providers', value: 5, suffix: '' },
  { label: 'Response Time', value: 0.3, suffix: 's', decimals: 1 }
];

export default function WelcomeHero({ onGetStarted, hasData }: WelcomeHeroProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setVisible(true);
  }, []);

  return (
    <div className="relative overflow-hidden">
      {/* Animated background elements */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 -right-40 h-80 w-80 rounded-full bg-gradient-to-br from-amber-500/30 via-pink-500/20 to-transparent blur-3xl animate-pulse-soft" />
        <div className="absolute -bottom-40 -left-40 h-80 w-80 rounded-full bg-gradient-to-tr from-sky-500/30 via-indigo-500/20 to-transparent blur-3xl animate-pulse-soft" style={{ animationDelay: '3s' }} />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-96 w-96 rounded-full bg-gradient-to-r from-amber-500/10 via-transparent to-sky-500/10 blur-3xl" />
      </div>

      <div className="relative">
        {/* Main hero section */}
        <div
          className={`text-center transition-all duration-1000 ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}
        >
          {/* Badge */}
          <div className="inline-flex items-center gap-2 rounded-full border border-amber-500/30 bg-amber-500/10 px-4 py-1.5 text-sm text-amber-300">
            <SparklesIcon className="h-4 w-4" />
            <span className="font-medium">Local AI Data Intelligence</span>
          </div>

          {/* Main heading */}
          <h1 className="mt-8 text-4xl font-bold leading-tight text-white sm:text-5xl lg:text-6xl">
            Your Data,{' '}
            <span className="bg-gradient-to-r from-amber-400 via-pink-500 to-sky-500 bg-clip-text text-transparent">
              Understood
            </span>
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-lg text-slate-400 leading-relaxed">
            Dawn is an AI-powered data copilot that ingests your spreadsheets, builds intelligent context,
            and answers questions with precision—all running locally on your machine.
          </p>

          {/* CTA buttons */}
          <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <button
              onClick={onGetStarted}
              className="group inline-flex items-center gap-3 rounded-full bg-gradient-to-r from-amber-400 via-pink-500 to-sky-500 px-8 py-4 text-lg font-semibold text-slate-900 shadow-xl shadow-amber-500/25 transition-all duration-300 hover:shadow-2xl hover:shadow-amber-500/40 hover:scale-105"
            >
              {hasData ? 'Continue Working' : 'Get Started'}
              <ArrowRightIcon className="h-5 w-5 transition-transform group-hover:translate-x-1" />
            </button>
          </div>

          {/* Stats */}
          <div className="mt-16 flex flex-wrap items-center justify-center gap-12">
            {stats.map((stat) => (
              <div key={stat.label} className="text-center">
                <div className="text-3xl font-bold text-white">
                  <AnimatedCounter
                    value={stat.value}
                    suffix={stat.suffix}
                    decimals={stat.decimals ?? 0}
                  />
                </div>
                <div className="mt-1 text-sm text-slate-500 uppercase tracking-wider">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Feature cards */}
        <div
          className={`mt-20 grid gap-6 sm:grid-cols-2 lg:grid-cols-4 transition-all duration-1000 delay-300 ${
            visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
          }`}
        >
          {features.map((feature, index) => (
            <div
              key={feature.title}
              className="transition-all duration-500"
              style={{ transitionDelay: `${400 + index * 100}ms` }}
            >
              <FeatureCard {...feature} />
            </div>
          ))}
        </div>

        {/* How it works preview */}
        <div
          className={`mt-20 rounded-3xl border border-white/10 bg-gradient-to-br from-slate-900/80 via-slate-900/60 to-slate-900/40 p-8 backdrop-blur-sm transition-all duration-1000 delay-500 ${
            visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
          }`}
        >
          <div className="text-center">
            <h2 className="text-2xl font-semibold text-white">How Dawn Works</h2>
            <p className="mt-2 text-slate-400">Three simple steps to data intelligence</p>
          </div>

          <div className="mt-10 grid gap-8 md:grid-cols-3">
            {[
              {
                step: 1,
                title: 'Upload & Profile',
                desc: 'Drop your Excel file and Dawn automatically profiles every column, detects data types, and identifies patterns.',
                icon: <TableCellsIcon className="h-8 w-8" />
              },
              {
                step: 2,
                title: 'AI Analysis',
                desc: 'The agent swarm creates an analysis plan, computes metrics, and builds a searchable knowledge base.',
                icon: <CpuChipIcon className="h-8 w-8" />
              },
              {
                step: 3,
                title: 'Ask Questions',
                desc: 'Query your data in plain English and get accurate, cited answers backed by real calculations.',
                icon: <ChatBubbleLeftRightIcon className="h-8 w-8" />
              }
            ].map((item, index) => (
              <div key={item.step} className="relative text-center">
                {index < 2 && (
                  <div className="absolute right-0 top-8 hidden h-0.5 w-8 bg-gradient-to-r from-amber-500/50 to-transparent md:block" style={{ right: '-1rem' }} />
                )}
                <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-amber-500/20 via-pink-500/10 to-sky-500/20 text-amber-400">
                  {item.icon}
                </div>
                <div className="mt-2 inline-flex h-6 w-6 items-center justify-center rounded-full bg-amber-500/20 text-xs font-bold text-amber-400">
                  {item.step}
                </div>
                <h3 className="mt-3 text-lg font-semibold text-white">{item.title}</h3>
                <p className="mt-2 text-sm text-slate-400 leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
