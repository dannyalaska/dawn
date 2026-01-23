'use client';

import { FormEvent, useState, useRef, useEffect, useCallback } from 'react';
import { PaperAirplaneIcon, CheckCircleIcon, CpuChipIcon } from '@heroicons/react/24/outline';
import { addContextNote, chatRag, fetchMemory, generateSql, updateMemory } from '@/lib/api';
import { useDawnSession } from '@/context/dawn-session';
import type { RagMessage } from '@/lib/types';
import clsx from 'clsx';

interface ContextChatPanelProps {
  disabled?: boolean;
  source?: string | null;
  activeFeedId?: string | null;
  memory?: { sha16: string; sheet: string } | null;
}

type DisplayMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  kind?: 'chat' | 'sql' | 'note';
  title?: string;
};

const buildMessageId = () => `${Date.now()}-${Math.random().toString(36).slice(2)}`;

const extractContextHint = (text: string) => {
  const columnMatch = text.match(
    /(column|field|metric)\s+([a-z0-9_ \-]+?)\s+(means|is|represents|refers to|indicates)\s+(.+)/i
  );
  if (columnMatch) {
    const column = columnMatch[2]?.trim();
    const definition = columnMatch[4]?.trim();
    if (column && definition) {
      return {
        note: `Column ${column} ${columnMatch[3]} ${definition}`,
        relationships: { [column]: definition }
      };
    }
  }

  const valueMatch = text.match(
    /(value|category|label)\s+["']?([^"']+)["']?\s+(means|is|represents|refers to|indicates)\s+(.+)/i
  );
  if (valueMatch) {
    const value = valueMatch[2]?.trim();
    const definition = valueMatch[4]?.trim();
    if (value && definition) {
      return {
        note: `Value ${value} ${valueMatch[3]} ${definition}`
      };
    }
  }

  return null;
};

export default function ContextChatPanel({ disabled, source, activeFeedId, memory }: ContextChatPanelProps) {
  const { token, apiBase } = useDawnSession();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const ragMessagesRef = useRef<RagMessage[]>([]);
  const demoAnswerRef = useRef<string | null>(null);
  const typingTimerRef = useRef<NodeJS.Timeout | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState('What changed in the latest upload?');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [sources, setSources] = useState<any[]>([]);
  const [pendingDemoQuestion, setPendingDemoQuestion] = useState<string | null>(null);
  const [pendingDemoAnswer, setPendingDemoAnswer] = useState<string | null>(null);
  const [demoTyping, setDemoTyping] = useState(false);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const persistContextHint = useCallback(
    async (question: string) => {
      if (!source || !memory) return;
      const hint = extractContextHint(question);
      if (!hint?.note) return;
      try {
        await addContextNote({ source, text: hint.note }, { token, apiBase });
        const existing = await fetchMemory(memory.sha16, memory.sheet, { token, apiBase });
        const nextRelationships = hint.relationships
          ? { ...(existing.relationships ?? {}), ...hint.relationships }
          : existing.relationships ?? {};
        const nextNotes = [...(existing.notes ?? [])];
        if (!nextNotes.includes(hint.note)) {
          nextNotes.push(hint.note);
        }
        await updateMemory(
          {
            sha16: memory.sha16,
            sheet: memory.sheet,
            relationships: nextRelationships,
            notes: nextNotes
          },
          { token, apiBase }
        );
      } catch (err) {
        console.warn('Failed to persist context hint', err);
      }
    },
    [apiBase, memory, source, token]
  );

  useEffect(() => {
    return () => {
      if (typingTimerRef.current) {
        clearTimeout(typingTimerRef.current);
      }
    };
  }, []);

  const sendQuestion = useCallback(async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || disabled || pending) return;
    setPending(true);
    setError('');
    const userMessage: RagMessage = { role: 'user', content: trimmed };
    ragMessagesRef.current = [...ragMessagesRef.current, userMessage];
    setMessages((prev) => [
      ...prev,
      { id: buildMessageId(), role: 'user', content: trimmed, kind: 'chat' }
    ]);

    void persistContextHint(trimmed);

    let sqlMessageId: string | null = null;
    if (activeFeedId) {
      sqlMessageId = buildMessageId();
      setMessages((prev) => [
        ...prev,
        {
          id: sqlMessageId,
          role: 'assistant',
          content: 'Generating SQL from your question…',
          kind: 'sql',
          title: 'NL → SQL agent'
        }
      ]);
      void generateSql(
        {
          question: trimmed,
          feed_identifiers: [activeFeedId],
          dialect: 'postgres',
          allow_writes: false
        },
        { token, apiBase }
      )
        .then((result) => {
          const sqlBlock = result.sql ? `\n${result.sql.trim()}` : 'No SQL generated.';
          const warnings = result.validation?.warnings?.length
            ? `\nWarnings: ${result.validation.warnings.join(' · ')}`
            : '';
          const errors = result.validation?.errors?.length
            ? `\nErrors: ${result.validation.errors.join(' · ')}`
            : '';
          const validationLabel = result.validation?.ok ? 'Validated' : 'Needs review';
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === sqlMessageId
                ? {
                    ...msg,
                    title: `NL → SQL agent · ${validationLabel}`,
                    content: `${sqlBlock}${warnings}${errors}`.trim()
                  }
                : msg
            )
          );
        })
        .catch((err) => {
          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === sqlMessageId
                ? {
                    ...msg,
                    title: 'NL → SQL agent · unavailable',
                    content: err instanceof Error ? err.message : 'Unable to generate SQL.'
                  }
                : msg
            )
          );
        });
    }
    try {
      const response = await chatRag(ragMessagesRef.current, { token, apiBase });
      let merged: RagMessage[] = [];
      if (response.messages && response.messages.length > 0) {
        merged = response.messages as RagMessage[];
      } else if (response.answer) {
        merged = [...ragMessagesRef.current, { role: 'assistant', content: response.answer }];
      } else {
        merged = ragMessagesRef.current;
      }
      ragMessagesRef.current = merged;
      const assistantMsg = merged[merged.length - 1];
      if (assistantMsg?.role === 'assistant') {
        setMessages((prev) => [
          ...prev,
          { id: buildMessageId(), role: 'assistant', content: assistantMsg.content, kind: 'chat' }
        ]);
      }
      setSources(response.sources || []);
      setInput('');
    } catch (err) {
      const fallback = demoAnswerRef.current;
      if (fallback) {
        ragMessagesRef.current = [...ragMessagesRef.current, { role: 'assistant', content: fallback }];
        setMessages((prev) => [
          ...prev,
          { id: buildMessageId(), role: 'assistant', content: fallback, kind: 'chat' }
        ]);
        setSources([]);
        setInput('');
        setError('');
      } else {
        setError(err instanceof Error ? err.message : 'Chat failed');
      }
    } finally {
      setPending(false);
      demoAnswerRef.current = null;
    }
  }, [activeFeedId, apiBase, disabled, pending, persistContextHint, token]);

  const startDemoTyping = useCallback(
    (question: string, demoAnswer?: string | null) => {
      const trimmed = question.trim();
      if (!trimmed) return;
      if (typingTimerRef.current) {
        clearTimeout(typingTimerRef.current);
      }
      demoAnswerRef.current = demoAnswer ?? null;
      setDemoTyping(true);
      setInput('');
      let index = 0;
      const step = () => {
        index += 1;
        setInput(trimmed.slice(0, index));
        if (index < trimmed.length) {
          typingTimerRef.current = setTimeout(step, 35);
        } else {
          setDemoTyping(false);
          void sendQuestion(trimmed);
        }
      };
      typingTimerRef.current = setTimeout(step, 60);
    },
    [sendQuestion]
  );

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendQuestion(input);
  }

  useEffect(() => {
    const handleDemoQuestion = (event: Event) => {
      const customEvent = event as CustomEvent;
      const question = customEvent.detail?.question ?? '';
      const demoAnswer = customEvent.detail?.demoAnswer ?? null;
      if (!question.trim()) return;
      if (disabled || pending || demoTyping) {
        setPendingDemoQuestion(question);
        setPendingDemoAnswer(demoAnswer);
      return;
    }
      startDemoTyping(question, demoAnswer);
    };

    window.addEventListener('demo:chat-question', handleDemoQuestion);
    return () => {
      window.removeEventListener('demo:chat-question', handleDemoQuestion);
    };
  }, [demoTyping, disabled, pending, startDemoTyping]);

  useEffect(() => {
    if (!pendingDemoQuestion || disabled || pending || demoTyping) return;
    startDemoTyping(pendingDemoQuestion, pendingDemoAnswer);
    setPendingDemoQuestion(null);
    setPendingDemoAnswer(null);
  }, [demoTyping, disabled, pending, pendingDemoAnswer, pendingDemoQuestion, startDemoTyping]);

  return (
    <div className="glass-panel rounded-3xl p-6 flex flex-col h-full">
      <div className="mb-4">
        <p className="text-xs uppercase tracking-[0.4em] text-slate-400">RAG chat</p>
        <h3 className="mt-2 text-lg font-semibold text-white">Ask questions about your data</h3>
      </div>

      {/* Messages area */}
      <div className="flex-1 h-64 sm:h-72 overflow-y-auto scroll-soft mb-4 space-y-3 pr-2">
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center text-sm text-slate-500">
            Index a workbook to start asking questions.
          </div>
        )}
        {messages.map((msg) => {
          const isUser = msg.role === 'user';
          const isSql = msg.kind === 'sql';
          return (
            <div
              key={msg.id}
              className={`animate-slide-up flex gap-3 ${isUser ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={clsx(
                  'max-w-xs rounded-2xl border px-4 py-2 text-sm leading-relaxed sm:max-w-sm',
                  isUser && 'bg-amber-500/20 border-amber-500/30 text-slate-100',
                  !isUser && !isSql && 'bg-sky-500/10 border-sky-500/20 text-slate-100',
                  isSql && 'bg-emerald-500/10 border-emerald-500/20 text-emerald-100'
                )}
              >
                {msg.title && (
                  <div className="mb-2 flex items-center gap-2 text-[11px] uppercase tracking-[0.3em] text-emerald-200">
                    <CpuChipIcon className="h-3 w-3" />
                    {msg.title}
                  </div>
                )}
                {isSql ? (
                  <pre className="whitespace-pre-wrap break-words text-xs text-emerald-100">{msg.content}</pre>
                ) : (
                  msg.content
                )}
              </div>
            </div>
          );
        })}
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
        {demoTyping && (
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.3em] text-amber-200">
            <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" />
            Auto-typing demo question
          </div>
        )}
        <textarea
          className="w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-white focus:border-sky-400 focus:ring-2 focus:ring-sky-400/20 disabled:opacity-50 resize-none"
          rows={3}
          value={input}
          disabled={pending || disabled || demoTyping}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask about your data..."
        />
        <button
          type="submit"
          disabled={pending || disabled || demoTyping || !input.trim()}
          className="w-full inline-flex items-center justify-center gap-2 rounded-full bg-gradient-to-r from-amber-400 via-pink-500 to-sky-500 px-4 py-2 text-sm font-semibold text-slate-900 shadow-aurora hover:shadow-lg disabled:opacity-50 transition-all"
        >
          <PaperAirplaneIcon className="h-4 w-4" />
          {pending ? 'Thinking…' : 'Send'}
        </button>
      </form>

      {disabled && (
        <p className="mt-2 text-xs text-slate-500 text-center">Index a workbook to unlock contextual chat.</p>
      )}
    </div>
  );
}
