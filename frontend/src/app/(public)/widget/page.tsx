'use client';

import { useEffect, useRef, useState } from 'react';
import { Bot, Send, User } from 'lucide-react';

type WidgetMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
};

export default function WidgetPage() {
  const [messages, setMessages] = useState<WidgetMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: 'Hi! Ask me about our projects, pricing, or book a site visit.',
    },
  ]);
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const sessionIdRef = useRef('');
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!sessionIdRef.current) {
      sessionIdRef.current =
        typeof crypto !== 'undefined' && crypto.randomUUID
          ? crypto.randomUUID()
          : `widget-${Date.now()}`;
    }
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || isSending) return;

    const userMessage: WidgetMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: text,
    };
    const assistantId = `a-${Date.now()}`;
    setMessages(prev => [...prev, userMessage, { id: assistantId, role: 'assistant', content: '' }]);
    setInput('');
    setIsSending(true);

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionIdRef.current,
          message: text,
        }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(data?.error || 'Chat request failed.');
      }
      const reply = typeof data?.reply === 'string' && data.reply
        ? data.reply
        : 'No reply received.';
      setMessages(prev =>
        prev.map(msg => msg.id === assistantId ? { ...msg, content: reply } : msg)
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Chat request failed.';
      setMessages(prev =>
        prev.map(msg => msg.id === assistantId ? { ...msg, content: message } : msg)
      );
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-zinc-950 px-4 py-16">
      <div className="mx-auto max-w-2xl">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
          Chat with Revenue OS
        </h1>
        <p className="mt-2 text-sm text-slate-600 dark:text-zinc-400">
          This widget talks to the live backend. No mock stream.
        </p>

        <div className="mt-8 flex h-[560px] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-lg dark:border-zinc-800 dark:bg-zinc-900">
          <div className="flex-1 space-y-4 overflow-y-auto p-5">
            {messages.map(msg => (
              <div
                key={msg.id}
                className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
              >
                <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${msg.role === 'user' ? 'bg-emerald-600 text-white' : 'bg-slate-100 text-slate-700 dark:bg-zinc-800 dark:text-zinc-200'}`}>
                  {msg.role === 'user' ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                </div>
                <div className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm ${msg.role === 'user' ? 'bg-emerald-600 text-white' : 'bg-slate-100 text-slate-800 dark:bg-zinc-800 dark:text-zinc-100'}`}>
                  {msg.content || (isSending ? '…' : '')}
                </div>
              </div>
            ))}
            <div ref={endRef} />
          </div>

          <div className="border-t border-slate-200 p-4 dark:border-zinc-800">
            <div className="relative">
              <input
                type="text"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && send()}
                placeholder="Type your message..."
                className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 pr-12 text-sm text-slate-900 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/30 dark:border-zinc-700 dark:bg-zinc-950 dark:text-white"
              />
              <button
                onClick={send}
                disabled={isSending || !input.trim()}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg bg-emerald-600 p-2 text-white transition-colors hover:bg-emerald-700 disabled:bg-slate-300 disabled:text-slate-500 dark:disabled:bg-zinc-800"
                aria-label="Send message"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
