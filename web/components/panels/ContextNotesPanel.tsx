'use client';

import { FormEvent, useState } from 'react';
import useDawnData from '@/hooks/useDawnData';
import { addContextNote, fetchContext, updateContextNote } from '@/lib/api';
import { useDawnSession } from '@/context/dawn-session';
import type { ContextNote } from '@/lib/types';

interface ContextNotesPanelProps {
  source: string | null;
}

export default function ContextNotesPanel({ source }: ContextNotesPanelProps) {
  const { token, apiBase } = useDawnSession();
  const [editing, setEditing] = useState<string | null>(null);
  const [editText, setEditText] = useState('');
  const [newNote, setNewNote] = useState('');
  const [error, setError] = useState('');
  const swr = useDawnData(source ? ['context', source] : null, ({ token, apiBase }) =>
    fetchContext(source!, 200, { token, apiBase })
  );

  const notes = swr.data?.notes ?? [];

  async function handleSave(note: ContextNote) {
    if (!editText.trim()) return;
    try {
      await updateContextNote(note.id, editText.trim(), { token, apiBase });
      setEditing(null);
      setEditText('');
      swr.mutate();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Update failed');
    }
  }

  async function handleAdd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!source || !newNote.trim()) return;
    try {
      await addContextNote({ source, text: newNote.trim() }, { token, apiBase });
      setNewNote('');
      swr.mutate();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Add failed');
    }
  }

  if (!source) {
    return (
      <div className="rounded-3xl border border-dashed border-white/15 p-6 text-sm text-slate-400">
        Select a feed/source to inspect its context notes.
      </div>
    );
  }

  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
      <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Context notes</p>
      <h3 className="mt-1 text-lg font-semibold text-white">{source}</h3>
      {error && <p className="mt-2 text-sm text-rose-400">{error}</p>}
      <div className="mt-4 max-h-80 space-y-3 overflow-y-auto pr-2">
        {swr.isLoading && <p className="text-sm text-slate-400">Loading notes…</p>}
        {notes.map((note) => (
          <div key={note.id} className="rounded-2xl border border-white/10 bg-black/30 p-4">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span>#{note.row_index >= 0 ? note.row_index : note.type}</span>
              <button
                type="button"
                className="text-amber-200"
                onClick={() => {
                  setEditing(note.id);
                  setEditText(note.text);
                }}
              >
                Edit
              </button>
            </div>
            {editing === note.id ? (
              <div className="mt-2 space-y-2">
                <textarea
                  className="w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-white"
                  value={editText}
                  onChange={(event) => setEditText(event.target.value)}
                  rows={3}
                />
                <div className="flex gap-2 text-xs">
                  <button
                    type="button"
                    className="rounded-full bg-emerald-500/80 px-3 py-1 text-slate-900"
                    onClick={() => handleSave(note)}
                  >
                    Save
                  </button>
                  <button
                    type="button"
                    className="rounded-full border border-white/10 px-3 py-1"
                    onClick={() => {
                      setEditing(null);
                      setEditText('');
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <p className="mt-2 text-sm text-slate-100 whitespace-pre-wrap">{note.text}</p>
            )}
          </div>
        ))}
        {!swr.isLoading && notes.length === 0 && (
          <p className="text-sm text-slate-400">No context notes yet.</p>
        )}
      </div>
      <form className="mt-4 space-y-2" onSubmit={handleAdd}>
        <textarea
          className="w-full rounded-2xl border border-white/10 bg-black/40 px-3 py-2 text-sm text-white"
          placeholder="Add guidance for this source"
          value={newNote}
          onChange={(event) => setNewNote(event.target.value)}
          rows={3}
        />
        <button
          type="submit"
          disabled={!newNote.trim()}
          className="rounded-full bg-gradient-to-r from-amber-400 via-pink-500 to-sky-500 px-4 py-2 text-sm font-semibold text-slate-900 shadow-aurora disabled:opacity-50"
        >
          Save note
        </button>
      </form>
    </div>
  );
}
