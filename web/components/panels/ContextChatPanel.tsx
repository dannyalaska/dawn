'use client';

import { FormEvent, useState, useRef, useEffect } from 'react';
import { PaperAirplaneIcon, CheckCircleIcon } from '@heroicons/react/24/outline';
import { chatRag } from '@/lib/api';
import { useDawnSession } from '@/context/dawn-session';
import type { RagMessage } from '@/lib/types';

interface ContextChatPanelProps {
  disabled?: boolean;
}

export default function ContextChatPanel({ disabled }: ContextChatPanelProps) {
  const { token, apiBase } = useDawnSession();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [messages, setMessages] = useState<RagMessage[]>([]);
  const [input, setInput] = useState('What changed in the latest upload?');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [sources, setSources] = useState<any[]>([]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!input.trim() || disabled) return;
    setPending(true);
    setError('');
    try {
      const nextMessages = [...messages, { role: 'user', content: input.trim() }];
      const response = await chatRag(nextMessages, { token, apiBase });
      let merged: RagMessage[] = [];
      if (response.messages && response.messages.length > 0) {
        merged = response.messages as RagMessage[];
      } else if (response.answer) {
        merged = [...nextMessages, { role: 'assistant', content: response.answer }];
      } else {
        merged = nextMessages;
      }
      setMessages(merged);
      setSources(response.sources || []);
      setInput('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Chat failed');
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="glass-panel rounded-3xl p-6 flex flex-col h-full">
      <div className="mb-4">
        <p className="text-xs uppercase tracking-[0.4em] text-slate-400">RAG chat</p>
        <h3 className="mt-2 text-lg font-semibold text-white">Ask questions about your data</h3>
      </div>

      {/* Messages area */}
      {messages.length > 0 && (
        <div className="flex-1 overflow-y-auto scroll-soft mb-4 space-y-3 pr-2">
          {messages.map((msg, idx) => (
            <div
              key={idx}
              className={`animate-slide-up flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-xs px-4 py-2 rounded-2xl text-sm leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-amber-500/20 border border-amber-500/30 text-slate-100'
                    : 'bg-sky-500/10 border border-sky-500/20 text-slate-100'
                }`}
              >
                {msg.content}
              </div>
            </div>
          ))}
          {pending && (
            <div className="flex justify-start">
              <div className="bg-slate-700/30 border border-slate-600/30 px-4 py-2 rounded-2xl">
                <div className="flex gap-1">
                  <div className="w-2 h-2 rounded-full bg-slate-400 animate-pulse" />
                  <div className="w-2 h-2 rounded-full bg-slate-400 animate-pulse" style={{ animationDelay: '0.1s' }} />
                  <div className="w-2 h-2 rounded-full bg-slate-400 animate-pulse" style={{ animationDelay: '0.2s' }} />
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      )}

      {/* Sources display */}
      {sources.length > 0 && (
        <div className="mb-3 p-2 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
          <p className="text-xs text-emerald-400 flex items-center gap-1 mb-1">
            <CheckCircleIcon className="h-3 w-3" />
            Sources
          </p>
          <div className="flex flex-wrap gap-1">
            {sources.slice(0, 3).map((s, idx) => (
              <span key={idx} className="text-xs bg-emerald-500/20 text-emerald-300 px-2 py-1 rounded">
                {s.source || 'context'}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Error message */}
      {error && (
        <p className="mb-3 text-sm text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-lg p-2">
          {error}
        </p>
      )}

      {/* Input form */}
      <form onSubmit={handleSubmit} className="space-y-3">
        <textarea
          className="w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-white focus:border-sky-400 focus:ring-2 focus:ring-sky-400/20 disabled:opacity-50 resize-none"
          rows={3}
          value={input}
          disabled={pending || disabled}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask about your data..."
        />
        <button
          type="submit"
          disabled={pending || disabled || !input.trim()}
          className="w-full inline-flex items-center justify-center gap-2 rounded-full bg-gradient-to-r from-amber-400 via-pink-500 to-sky-500 px-4 py-2 text-sm font-semibold text-slate-900 shadow-aurora hover:shadow-lg disabled:opacity-50 transition-all"
        >
          <PaperAirplaneIcon className="h-4 w-4" />
          {pending ? 'Thinking…' : 'Send'}
        </button>
      </form>

      {/* Empty state */}
      {messages.length === 0 && !disabled && (
        <div className="flex flex-col items-center justify-center flex-1 text-center">
          <p className="text-slate-500 text-sm">Index a workbook to start asking questions.</p>
        </div>
      )}

      {disabled && (
        <p className="mt-2 text-xs text-slate-500 text-center">Index a workbook to unlock contextual chat.</p>
      )}
    </div>
  );
}
