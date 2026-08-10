'use client';

import React, { useState, useEffect, useCallback, Suspense } from 'react';
import dynamic from 'next/dynamic';
import {
  MessageCircle,
  DollarSign,
  Calendar,
  UserPlus,
  Cpu,
  AlertCircle,
  Search,
  Filter,
  Network,
} from 'lucide-react';
import { useSearchParams, useRouter } from 'next/navigation';
import {
  runSalesAi,
  fetchLeadOptions,
  fetchNeighborhood,
} from './actions';
import SalesAiModal, { type SalesAiResult } from '@/components/SalesAiModal';

type TimelineEvent = {
  id: string;
  type: string;
  title: string;
  description: string;
  timestamp: string;
  actor: string;
  amount?: number;
};

type LeadOpt = { id: string; label: string; temperature: string };

const GraphWrapper = dynamic(
  () => import('../knowledge-graph/GraphWrapper'),
  {
    ssr: false,
    loading: () => (
      <div className="h-48 flex items-center justify-center text-xs text-gray-500">
        Loading graph…
      </div>
    ),
  }
);

function SalesCopilotContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const paramLead = searchParams.get('lead_id');

  const [leadOptions, setLeadOptions] = useState<LeadOpt[]>([]);
  const [leadId, setLeadId] = useState(paramLead || '');
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [filter, setFilter] = useState('all');

  const [salesAIResult, setSalesAIResult] = useState<SalesAiResult | null>(null);
  const [isSalesAILoading, setIsSalesAILoading] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [salesError, setSalesError] = useState<string | null>(null);

  const [graphData, setGraphData] = useState<{ nodes: unknown[]; edges: unknown[] }>({
    nodes: [],
    edges: [],
  });
  const [graphAvailable, setGraphAvailable] = useState(true);
  const [graphSummary, setGraphSummary] = useState('');

  useEffect(() => {
    fetchLeadOptions()
      .then((opts) => {
        setLeadOptions(opts);
        if (!paramLead && opts.length > 0) {
          setLeadId(opts[0].id);
        } else if (paramLead) {
          setLeadId(paramLead);
        }
      })
      .catch(() => setLeadOptions([]));
  }, [paramLead]);

  const loadTimeline = useCallback(async (id: string) => {
    if (!id) return;
    try {
      const res = await fetch(`/api/v1/events/leads/${id}/timeline`, {
        credentials: 'include',
      });
      if (res.ok) {
        const data = await res.json();
        const mapped = (data.events || []).map(
          (evt: {
            event_id: string;
            event_type: string;
            payload?: Record<string, string>;
            source?: string;
            timestamp?: string;
          }) => ({
            id: evt.event_id,
            type: evt.event_type,
            title: evt.event_type.replace(/_/g, ' ').toUpperCase(),
            description: evt.payload?.action_type || evt.source || 'Timeline event recorded.',
            timestamp: evt.timestamp || new Date().toISOString(),
            actor: evt.payload?.agent_type || 'System',
          })
        );
        setEvents(mapped);
      } else if (res.status === 404) {
        setEvents([]);
      } else {
        setEvents([]);
      }
    } catch {
      setEvents([]);
    }
  }, []);

  const loadGraph = useCallback(async (id: string) => {
    if (!id) return;
    try {
      const data = await fetchNeighborhood(id);
      setGraphAvailable(Boolean(data.available));
      setGraphSummary(data.ai_summary || '');
      setGraphData({
        nodes: data.data?.nodes || [],
        edges: data.data?.edges || [],
      });
    } catch {
      setGraphAvailable(false);
      setGraphData({ nodes: [], edges: [] });
    }
  }, []);

  useEffect(() => {
    if (!leadId) return;
    const t = window.setTimeout(() => {
      void loadTimeline(leadId);
      void loadGraph(leadId);
    }, 0);
    return () => window.clearTimeout(t);
  }, [leadId, loadTimeline, loadGraph]);

  // SSE: refetch graph/timeline on relevant events for selected lead
  useEffect(() => {
    if (!leadId) return;
    const es = new EventSource('/api/v1/events/stream', { withCredentials: true });
    es.onmessage = (event) => {
      if (!event.data || event.data.startsWith(':')) return;
      try {
        const data = JSON.parse(event.data);
        const t = data.event_type as string;
        const entity = String(data.entity_id || data.payload?.lead_id || '');
        const match =
          entity === leadId ||
          entity === `lead:${leadId}` ||
          entity.endsWith(`_${leadId}`) ||
          String(data.payload?.lead_id) === leadId;
        if (!match) return;
        if (t === 'lead.scored' || t === 'lead.assigned' || t === 'lead.hot') {
          loadGraph(leadId);
          loadTimeline(leadId);
        }
        if (t?.startsWith('lead.') || t?.includes('whatsapp') || t === 'conversation.updated') {
          loadTimeline(leadId);
        }
      } catch {
        /* ignore parse / ping */
      }
    };
    es.onerror = () => {
      /* browser auto-reconnects */
    };
    return () => es.close();
  }, [leadId, loadGraph, loadTimeline]);

  const onLeadChange = (id: string) => {
    setLeadId(id);
    const sp = new URLSearchParams(searchParams.toString());
    if (id) sp.set('lead_id', id);
    else sp.delete('lead_id');
    router.replace(`?${sp.toString()}`);
  };

  const handlePreview = async () => {
    if (!leadId) return;
    setIsSalesAILoading(true);
    setSalesError(null);
    try {
      const data = await runSalesAi(leadId, 'preview');
      setSalesAIResult(data);
      setIsPreviewOpen(true);
    } catch (err) {
      setSalesError(err instanceof Error ? err.message : 'Preview failed');
      setIsPreviewOpen(true);
      setSalesAIResult(null);
    } finally {
      setIsSalesAILoading(false);
    }
  };

  const handleConfirm = async () => {
    if (!leadId || isExecuting) return;
    setIsExecuting(true);
    setSalesError(null);
    try {
      const data = await runSalesAi(leadId, 'execute');
      setSalesAIResult(data);
      await loadTimeline(leadId);
      await loadGraph(leadId);
      setTimeout(() => setIsPreviewOpen(false), 800);
    } catch (err) {
      setSalesError(err instanceof Error ? err.message : 'Execute failed');
    } finally {
      setIsExecuting(false);
    }
  };

  const filteredEvents = events.filter((e) => {
    if (filter === 'all') return true;
    if (filter === 'communications')
      return e.type.includes('whatsapp') || e.type.includes('email') || e.type.includes('call');
    if (filter === 'payments') return e.type === 'payment.received';
    if (filter === 'system')
      return (
        e.type === 'system.alert' ||
        e.type === 'site_visit.scheduled' ||
        e.type === 'lead.created'
      );
    if (filter === 'ai') return e.type === 'ai.insight' || e.type.includes('scored');
    return true;
  });

  const selectedLabel =
    leadOptions.find((o) => o.id === leadId)?.label || (leadId ? `Lead ${leadId}` : 'Select lead');

  const getEventIcon = (type: string) => {
    if (type.includes('whatsapp')) return <MessageCircle className="w-5 h-5 text-green-400" />;
    if (type.includes('payment')) return <DollarSign className="w-5 h-5 text-emerald-400" />;
    if (type.includes('site_visit')) return <Calendar className="w-5 h-5 text-blue-400" />;
    if (type.includes('lead')) return <UserPlus className="w-5 h-5 text-purple-400" />;
    if (type.includes('ai') || type.includes('scored'))
      return <Cpu className="w-5 h-5 text-indigo-400" />;
    return <AlertCircle className="w-5 h-5 text-gray-400" />;
  };

  const getEventBg = (type: string) => {
    if (type.includes('whatsapp')) return 'bg-green-500/10 border-green-500/20';
    if (type.includes('payment')) return 'bg-emerald-500/10 border-emerald-500/20';
    if (type.includes('site_visit')) return 'bg-blue-500/10 border-blue-500/20';
    if (type.includes('lead')) return 'bg-purple-500/10 border-purple-500/20';
    if (type.includes('ai') || type.includes('scored')) return 'bg-indigo-500/10 border-indigo-500/20';
    return 'bg-gray-800/50 border-gray-700';
  };

  return (
    <div className="max-w-6xl mx-auto flex gap-6 h-[calc(100vh-8rem)]">
      <div className="w-1/3 flex flex-col gap-4 hidden lg:flex min-h-0">
        <div className="bg-[#13131a] border border-gray-800 rounded-2xl p-5 shadow-xl shrink-0">
          <label className="text-xs text-gray-500 uppercase font-bold tracking-wider block mb-2">
            Selected lead
          </label>
          <select
            value={leadId}
            onChange={(e) => onLeadChange(e.target.value)}
            className="w-full bg-[#0f0f13] border border-gray-700 text-white text-sm rounded-lg px-3 py-2"
          >
            {leadOptions.length === 0 && <option value={leadId || ''}>{selectedLabel}</option>}
            {leadOptions.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label} (#{o.id})
              </option>
            ))}
          </select>
          <p className="text-xs text-gray-500 mt-2">ID: {leadId || '—'}</p>
        </div>

        <div className="bg-gradient-to-b from-[#1a1a2e] to-[#13131a] border border-indigo-900/30 rounded-2xl p-5 shadow-xl flex flex-col shrink-0">
          <h3 className="text-lg font-bold text-white mb-2 flex items-center gap-2">
            <Cpu className="w-5 h-5 text-indigo-400" />
            Sales Copilot
          </h3>
          <p className="text-sm text-gray-400 mb-4">
            Preview recommendation first, then confirm to apply.
          </p>
          <button
            type="button"
            onClick={handlePreview}
            disabled={isSalesAILoading || !leadId}
            className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-xl transition-colors shadow-lg shadow-indigo-900/20 disabled:opacity-50"
          >
            {isSalesAILoading ? 'Analyzing…' : 'Get recommendation'}
          </button>
        </div>

        <div className="flex-1 min-h-[200px] bg-[#13131a] border border-gray-800 rounded-2xl overflow-hidden flex flex-col">
          <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-2">
            <Network className="w-4 h-4 text-purple-400" />
            <span className="text-sm font-semibold text-white">Ego network</span>
          </div>
          {!graphAvailable || graphData.nodes.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center p-4 text-center text-xs text-gray-500">
              <p>Graph unavailable or empty.</p>
              <p className="mt-1 text-gray-600">
                {graphSummary || 'Neo4j down or FEATURE_GRAPH_VIZ=false'}
              </p>
            </div>
          ) : (
            <div className="flex-1 min-h-[180px]">
              <GraphWrapper
                data={graphData as { nodes: Record<string, unknown>[]; edges: Record<string, unknown>[] }}
                onNodeClick={() => {}}
              />
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 flex flex-col bg-[#0a0a0a] rounded-2xl border border-gray-800 shadow-xl overflow-hidden min-h-0">
        <div className="p-5 border-b border-gray-800 bg-[#0f0f13] sticky top-0 z-10">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <Filter className="w-5 h-5 text-gray-400" />
              Event Timeline
            </h2>
            <div className="relative lg:hidden">
              <select
                value={leadId}
                onChange={(e) => onLeadChange(e.target.value)}
                className="bg-[#15151a] border border-gray-700 text-sm text-white rounded-lg px-3 py-2"
              >
                {leadOptions.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="relative hidden md:block">
              <Search className="w-4 h-4 text-gray-500 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search events…"
                className="bg-[#15151a] border border-gray-700 text-sm text-white rounded-lg pl-9 pr-4 py-2 focus:outline-none focus:border-indigo-500"
              />
            </div>
          </div>
          <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
            {['all', 'communications', 'payments', 'system', 'ai'].map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                className={`px-4 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors capitalize ${
                  filter === f
                    ? 'bg-indigo-600 text-white shadow-md'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white'
                }`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {filteredEvents.length === 0 ? (
            <p className="text-sm text-gray-500 text-center py-12">
              No timeline events for this lead.
            </p>
          ) : (
            <div className="relative space-y-6 before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-gray-800 before:to-transparent">
              {filteredEvents.map((event) => (
                <div
                  key={event.id}
                  className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group"
                >
                  <div
                    className={`flex items-center justify-center w-10 h-10 rounded-full border-4 border-[#0a0a0a] shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 shadow-xl z-10 ${getEventBg(event.type).split(' ')[0]}`}
                  >
                    {getEventIcon(event.type)}
                  </div>
                  <div
                    className={`w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] p-4 rounded-xl border ${getEventBg(event.type)}`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-bold text-gray-400 uppercase tracking-wider">
                        {event.actor}
                      </span>
                      <time className="text-xs text-gray-500 font-mono">
                        {new Date(event.timestamp).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </time>
                    </div>
                    <h4 className="text-sm font-bold text-white mb-1">{event.title}</h4>
                    <p className="text-sm text-gray-300 leading-relaxed">{event.description}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {isPreviewOpen && (salesAIResult || salesError) && (
        <SalesAiModal
          result={salesAIResult || {}}
          isExecuting={isExecuting}
          error={salesError}
          onCancel={() => {
            setIsPreviewOpen(false);
            setSalesError(null);
          }}
          onConfirm={handleConfirm}
        />
      )}
    </div>
  );
}

export default function SalesCopilotPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-screen items-center justify-center text-white">Loading Copilot…</div>
      }
    >
      <SalesCopilotContent />
    </Suspense>
  );
}
