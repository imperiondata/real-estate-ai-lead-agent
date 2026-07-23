'use client';

import React, { useState, useEffect } from 'react';
// Removed mock timeline import; using real types below.
type TimelineEvent = {
  id: string;
  type: string;
  title: string;
  description: string;
  timestamp: string;
  actor: string;
  amount?: number;
};
import { MessageCircle, DollarSign, Calendar, UserPlus, Cpu, AlertCircle, Search, Filter } from 'lucide-react';

export default function SalesCopilotPage() {
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [filter, setFilter] = useState<string>('all');

  useEffect(() => {
    const fetchTimeline = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const res = await fetch(`${apiUrl}/api/v1/events/leads/1/timeline?api_key=secret-client-key-123`, {
          // Send cookies if available
          credentials: 'omit' // use api_key for now to bypass CORS cookie issues during dev
        });
        if (res.ok) {
          const data = await res.json();
          const mappedEvents = data.events.map((evt: any) => ({
            id: evt.event_id,
            type: evt.event_type,
            title: evt.event_type.replace(/_/g, ' ').toUpperCase(),
            description: evt.payload?.action_type || evt.source || 'Timeline event recorded.',
            timestamp: evt.timestamp || new Date().toISOString(),
            actor: evt.payload?.agent_type || 'System',
          }));
          setEvents(mappedEvents);
        } else {
          console.error("Failed to fetch timeline");
        }
      } catch (err) {
        console.error("Error fetching timeline:", err);
      }
    };
    fetchTimeline();
  }, []);

  const filteredEvents = events.filter(e => {
    if (filter === 'all') return true;
    if (filter === 'communications') return e.type.includes('whatsapp') || e.type.includes('email') || e.type.includes('call');
    if (filter === 'payments') return e.type === 'payment.received';
    if (filter === 'system') return e.type === 'system.alert' || e.type === 'site_visit.scheduled' || e.type === 'lead.created';
    if (filter === 'ai') return e.type === 'ai.insight';
    return true;
  });

  const getEventIcon = (type: string) => {
    if (type.includes('whatsapp')) return <MessageCircle className="w-5 h-5 text-green-400" />;
    if (type.includes('payment')) return <DollarSign className="w-5 h-5 text-emerald-400" />;
    if (type.includes('site_visit')) return <Calendar className="w-5 h-5 text-blue-400" />;
    if (type.includes('lead')) return <UserPlus className="w-5 h-5 text-purple-400" />;
    if (type.includes('ai.insight')) return <Cpu className="w-5 h-5 text-indigo-400" />;
    return <AlertCircle className="w-5 h-5 text-gray-400" />;
  };

  const getEventBg = (type: string) => {
    if (type.includes('whatsapp')) return 'bg-green-500/10 border-green-500/20';
    if (type.includes('payment')) return 'bg-emerald-500/10 border-emerald-500/20';
    if (type.includes('site_visit')) return 'bg-blue-500/10 border-blue-500/20';
    if (type.includes('lead')) return 'bg-purple-500/10 border-purple-500/20';
    if (type.includes('ai.insight')) return 'bg-indigo-500/10 border-indigo-500/20';
    return 'bg-gray-800/50 border-gray-700';
  };

  return (
    <div className="max-w-5xl mx-auto flex gap-6 h-[calc(100vh-8rem)]">
      
      {/* Left Column: Context & Copilot (Mock) */}
      <div className="w-1/3 flex flex-col gap-6 hidden lg:flex">
        <div className="bg-[#13131a] border border-gray-800 rounded-2xl p-6 shadow-xl">
          <div className="w-16 h-16 rounded-full bg-gradient-to-tr from-purple-500 to-indigo-500 flex items-center justify-center text-xl font-bold text-white mb-4">
            JD
          </div>
          <h2 className="text-xl font-bold text-white">John Doe</h2>
          <p className="text-sm text-gray-400 mb-4">Interested in: Tower B, Unit 205</p>
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-gray-500">Intent Score</span>
              <span className="text-red-400 font-bold">92 (Hot)</span>
            </div>
            <div className="w-full bg-gray-800 rounded-full h-1.5">
              <div className="bg-red-500 h-1.5 rounded-full" style={{ width: '92%' }}></div>
            </div>
          </div>
        </div>

        <div className="flex-1 bg-gradient-to-b from-[#1a1a2e] to-[#13131a] border border-indigo-900/30 rounded-2xl p-6 shadow-xl flex flex-col">
          <h3 className="text-lg font-bold text-white mb-2 flex items-center gap-2">
            <Cpu className="w-5 h-5 text-indigo-400" />
            Sales Copilot
          </h3>
          <p className="text-sm text-gray-400 mb-6">AI analysis of this lead's timeline.</p>
          
          <div className="space-y-4 flex-1">
            <div className="p-4 rounded-xl bg-indigo-950/30 border border-indigo-900/50">
              <p className="text-sm text-indigo-200 leading-relaxed">
                John has highly engaged with the floorplan sent via WhatsApp. A site visit is scheduled. **Next Action:** Ensure FinanceAgent sends the pre-approval payment link before the visit.
              </p>
            </div>
          </div>
          
          <button className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-xl transition-colors shadow-lg shadow-indigo-900/20">
            Generate Email Draft
          </button>
        </div>
      </div>

      {/* Right Column: Timeline Feed */}
      <div className="flex-1 flex flex-col bg-[#0a0a0a] rounded-2xl border border-gray-800 shadow-xl overflow-hidden">
        
        {/* Header & Filters */}
        <div className="p-5 border-b border-gray-800 bg-[#0f0f13] sticky top-0 z-10">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <Filter className="w-5 h-5 text-gray-400" />
              Event Timeline
            </h2>
            <div className="relative">
              <Search className="w-4 h-4 text-gray-500 absolute left-3 top-1/2 -translate-y-1/2" />
              <input type="text" placeholder="Search events..." className="bg-[#15151a] border border-gray-700 text-sm text-white rounded-lg pl-9 pr-4 py-2 focus:outline-none focus:border-indigo-500" />
            </div>
          </div>
          
          <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide">
            {['all', 'communications', 'payments', 'system', 'ai'].map((f) => (
              <button
                key={f}
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

        {/* Vertical Feed */}
        <div className="flex-1 overflow-y-auto p-6">
          <div className="relative space-y-6 before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-gray-800 before:to-transparent">
            {filteredEvents.map((event) => (
              <div key={event.id} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">
                
                {/* Timeline Icon */}
                <div className={`flex items-center justify-center w-10 h-10 rounded-full border-4 border-[#0a0a0a] shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 shadow-xl z-10 ${getEventBg(event.type).split(' ')[0]}`}>
                  {getEventIcon(event.type)}
                </div>
                
                {/* Event Card */}
                <div className={`w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] p-4 rounded-xl border ${getEventBg(event.type)}`}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-bold text-gray-400 uppercase tracking-wider">{event.actor}</span>
                    <time className="text-xs text-gray-500 font-mono">
                      {new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </time>
                  </div>
                  <h4 className="text-sm font-bold text-white mb-1">{event.title}</h4>
                  <p className="text-sm text-gray-300 leading-relaxed">{event.description}</p>
                  
                  {event.amount && (
                    <div className="mt-3 inline-block bg-emerald-500/20 text-emerald-400 text-xs font-bold px-3 py-1.5 rounded-lg border border-emerald-500/30">
                      + ${event.amount.toLocaleString()}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
