'use client';

import React, { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { mockGraphResponse } from '@/lib/api/mockGraphService';
import { Filter, Layers, Zap, X, ShieldAlert, Cpu } from 'lucide-react';

// ForceGraph relies on canvas and window APIs. Must dynamically import with SSR disabled.
const GraphWrapper = dynamic(() => import('./GraphWrapper'), { 
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex items-center justify-center bg-[#0a0a0a]">
      <div className="animate-pulse flex flex-col items-center">
        <div className="w-12 h-12 rounded-full border-4 border-blue-500 border-t-transparent animate-spin mb-4"></div>
        <p className="text-blue-400 font-medium">Initializing Graph Physics...</p>
      </div>
    </div>
  )
});

export default function KnowledgeGraphPage() {
  const [data, setData] = useState({ nodes: [], edges: [] });
  const [filteredData, setFilteredData] = useState({ nodes: [], edges: [] });
  const [selectedNode, setSelectedNode] = useState<any | null>(null);
  
  // Filters State
  const [showComms, setShowComms] = useState(true);
  const [onlyHotLeads, setOnlyHotLeads] = useState(false);

  useEffect(() => {
    // Load mock data
    const rawData = mockGraphResponse.data as any;
    setData(rawData);
    setFilteredData(rawData);
  }, []);

  // Apply filters
  useEffect(() => {
    let newNodes = [...data.nodes];
    
    if (!showComms) {
      newNodes = newNodes.filter((n: any) => n.label !== 'Communication');
    }
    
    if (onlyHotLeads) {
      // Keep only hot leads, projects, towers, units. Hide warm/cold leads.
      newNodes = newNodes.filter((n: any) => {
        if (n.label === 'Lead') return n.properties.temperature === 'Hot';
        if (n.label === 'Communication') return false; // Hot leads focus usually ignores comms clutter
        return true; 
      });
    }

    const nodeIds = new Set(newNodes.map((n: any) => n.id));
    const newEdges = data.edges.filter((e: any) => 
      nodeIds.has(e.source.id || e.source) && nodeIds.has(e.target.id || e.target)
    );

    setFilteredData({ nodes: newNodes, edges: newEdges } as any);
  }, [showComms, onlyHotLeads, data]);

  return (
    <div className="relative w-full h-[calc(100vh-4rem)] -m-6 md:-m-8 overflow-hidden bg-[#0a0a0a]">
      {/* Alert Banner */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-50 bg-blue-900/90 border border-blue-500/50 text-blue-100 px-6 py-2 rounded-full shadow-lg backdrop-blur-sm text-sm font-medium whitespace-nowrap flex items-center gap-2 pointer-events-none">
        <Zap className="w-4 h-4 text-blue-400" />
        Phase 4 Development: Integrating Neo4j Live Data. Expected Completion: September 3, 2026
      </div>
      
      {/* 1. The Canvas */}
      <GraphWrapper 
        data={filteredData} 
        onNodeClick={(node) => setSelectedNode(node)} 
      />

      {/* 2. Floating Control Panel (Left) */}
      <div className="absolute top-6 left-6 w-72 bg-[#0f0f13]/80 backdrop-blur-xl border border-gray-800 rounded-2xl shadow-2xl overflow-hidden z-10">
        <div className="p-4 border-b border-gray-800 bg-[#15151a]/50 flex items-center gap-2">
          <Layers className="w-5 h-5 text-blue-400" />
          <h2 className="text-sm font-bold text-white tracking-wide uppercase">Graph Controls</h2>
        </div>
        
        <div className="p-5 space-y-5">
          <div className="space-y-3">
            <label className="flex items-center justify-between cursor-pointer group">
              <span className="text-sm font-medium text-gray-300 group-hover:text-white transition-colors">Show Communications</span>
              <input 
                type="checkbox" 
                checked={showComms}
                onChange={(e) => setShowComms(e.target.checked)}
                className="w-4 h-4 rounded bg-gray-900 border-gray-700 text-blue-500 focus:ring-blue-500 focus:ring-offset-gray-900"
              />
            </label>
            <label className="flex items-center justify-between cursor-pointer group">
              <span className="text-sm font-medium text-gray-300 group-hover:text-white transition-colors">Only Hot Leads</span>
              <input 
                type="checkbox" 
                checked={onlyHotLeads}
                onChange={(e) => setOnlyHotLeads(e.target.checked)}
                className="w-4 h-4 rounded bg-gray-900 border-gray-700 text-red-500 focus:ring-red-500 focus:ring-offset-gray-900"
              />
            </label>
          </div>

          <div className="pt-4 border-t border-gray-800">
            <p className="text-xs text-gray-500 mb-2 font-semibold uppercase">Legend</p>
            <div className="grid grid-cols-2 gap-2 text-xs text-gray-400">
              <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-[#ef4444]"></div> Hot Lead</div>
              <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-[#f59e0b]"></div> Warm Lead</div>
              <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-[#3b82f6]"></div> Cold Lead / Proj</div>
              <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-[#10b981]"></div> Available Unit</div>
              <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-[#8b5cf6]"></div> Tower</div>
              <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full bg-[#64748b]"></div> Comm / Log</div>
            </div>
          </div>
        </div>
      </div>

      {/* 3. Right Sidebar (Node Details & AI Actions) */}
      <div className={`absolute top-0 right-0 w-80 h-full bg-[#0f0f13]/95 backdrop-blur-2xl border-l border-gray-800 shadow-2xl transition-transform duration-300 ease-in-out z-20 ${selectedNode ? 'translate-x-0' : 'translate-x-full'}`}>
        {selectedNode && (
          <div className="flex flex-col h-full">
            {/* Header */}
            <div className="p-6 border-b border-gray-800 flex items-start justify-between">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-blue-400 mb-1 block">{selectedNode.label}</span>
                <h2 className="text-xl font-bold text-white truncate max-w-[200px]">
                  {selectedNode.properties?.name || selectedNode.properties?.unit_number || selectedNode.properties?.type}
                </h2>
              </div>
              <button onClick={() => setSelectedNode(null)} className="p-1.5 hover:bg-gray-800 rounded-lg text-gray-400 hover:text-white transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Properties */}
            <div className="p-6 flex-1 overflow-y-auto space-y-6">
              <div className="space-y-4">
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Properties</h3>
                <div className="grid grid-cols-1 gap-3">
                  {Object.entries(selectedNode.properties || {}).map(([key, val]) => (
                    <div key={key} className="bg-gray-900/50 p-3 rounded-lg border border-gray-800">
                      <p className="text-xs text-gray-500 mb-0.5 capitalize">{key.replace('_', ' ')}</p>
                      <p className="text-sm font-medium text-gray-200">{String(val)}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Simulated AI Suggestions for Leads */}
              {selectedNode.label === 'Lead' && (
                <div className="pt-6 border-t border-gray-800">
                  <h3 className="text-xs font-semibold text-purple-400 uppercase tracking-wider flex items-center gap-2 mb-4">
                    <Cpu className="w-4 h-4" />
                    AI Suggested Actions
                  </h3>
                  
                  <div className="space-y-3">
                    <button className="w-full text-left p-3 rounded-xl bg-purple-500/10 border border-purple-500/20 hover:bg-purple-500/20 transition-colors group">
                      <div className="flex items-center gap-2 mb-1">
                        <Zap className="w-4 h-4 text-purple-400" />
                        <span className="text-sm font-medium text-purple-300">Draft WhatsApp Follow-up</span>
                      </div>
                      <p className="text-xs text-purple-400/70">Based on recent site visit context.</p>
                    </button>
                    
                    {selectedNode.properties.temperature === 'Hot' && (
                      <button className="w-full text-left p-3 rounded-xl bg-red-500/10 border border-red-500/20 hover:bg-red-500/20 transition-colors">
                        <div className="flex items-center gap-2 mb-1">
                          <ShieldAlert className="w-4 h-4 text-red-400" />
                          <span className="text-sm font-medium text-red-300">Escalate to Sales Manager</span>
                        </div>
                        <p className="text-xs text-red-400/70">High intent score (90+) detected.</p>
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

    </div>
  );
}
