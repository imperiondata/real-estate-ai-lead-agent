'use client';

import React, { useEffect, useState } from 'react';
import { useCommandCenterStore } from '@/lib/store/useCommandCenterStore';
import { mockForecastData, mockChartData } from '@/lib/api/mockService';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { TrendingUp, Users, DollarSign, Activity, AlertTriangle, Info, BellRing, Bot } from 'lucide-react';

export default function ExecutiveDashboardPage() {
  const { activeProjectId } = useCommandCenterStore();
  
  // State for mocked SSE data
  const [kpis, setKpis] = useState({ totalRevenue: 0, pipelineValue: 0, activeAgents: 0, leadVelocity: 0 });
  const [alerts, setAlerts] = useState<any[]>([]);
  const [forecast, setForecast] = useState<any>(null);

  useEffect(() => {
    // Initial fetch of forecast API
    setForecast(mockForecastData.forecast);

    // Live SSE Connection
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const eventSource = new EventSource(`${apiUrl}/api/v1/events/stream?api_key=secret-client-key-123`, {
      withCredentials: false // using api key for dev
    });

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        // Artificial demo mapping: map real event stream into frontend UI state
        if (data.event_type === 'lead.created') {
          setKpis(prev => ({ ...prev, pipelineValue: prev.pipelineValue + 150000, leadVelocity: prev.leadVelocity + 1 }));
          setAlerts(prev => [{ id: data.event_id, type: 'info', message: `New Lead Created (${data.entity_id})`, timestamp: new Date().toLocaleTimeString() }, ...prev].slice(0, 5));
        } else if (data.event_type === 'approval.requested') {
          setAlerts(prev => [{ id: data.event_id, type: 'warning', message: 'Approval Requested', timestamp: new Date().toLocaleTimeString() }, ...prev].slice(0, 5));
        } else if (data.event_type === 'lead.scored') {
          setAlerts(prev => [{ id: data.event_id, type: 'info', message: `Lead Scored`, timestamp: new Date().toLocaleTimeString() }, ...prev].slice(0, 5));
        } else if (data.event_type === 'marketing.report.generated') {
          setKpis(prev => ({ ...prev, totalRevenue: prev.totalRevenue + 50000 }));
          setAlerts(prev => [{ id: data.event_id, type: 'info', message: 'Marketing Report Generated', timestamp: new Date().toLocaleTimeString() }, ...prev].slice(0, 5));
        } else {
          // Generic fallback for other events
          setAlerts(prev => [{ id: data.event_id || Date.now().toString(), type: 'info', message: `Event: ${data.event_type}`, timestamp: new Date().toLocaleTimeString() }, ...prev].slice(0, 5));
        }
      } catch (err) {
        console.error("SSE parsing error:", err);
      }
    };

    eventSource.onerror = (err) => {
      console.error("EventSource error:", err);
    };

    return () => eventSource.close();
  }, [activeProjectId]);

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value);
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-10">
      
      {/* Date / Project Selectors (Mocked for UI) */}
      <div className="flex justify-end gap-3 mb-6">
        <select className="bg-gray-900 border border-gray-800 text-gray-300 text-sm rounded-lg px-4 py-2 focus:ring-blue-500 focus:border-blue-500 outline-none">
          <option>Project: PRJ-101 (The Summit)</option>
          <option>Project: PRJ-205 (Oasis Heights)</option>
        </select>
        <select className="bg-gray-900 border border-gray-800 text-gray-300 text-sm rounded-lg px-4 py-2 focus:ring-blue-500 focus:border-blue-500 outline-none">
          <option>Last 30 Days</option>
          <option>This Quarter</option>
          <option>Year to Date</option>
        </select>
      </div>

      {/* TOP ROW: KPI Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        
        {/* KPI 1 */}
        <div className="bg-[#13131a] border border-gray-800/60 rounded-2xl p-5 shadow-lg relative overflow-hidden group">
          <div className="absolute inset-0 bg-gradient-to-br from-blue-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
          <div className="flex justify-between items-start mb-4">
            <div className="p-2 bg-blue-500/10 rounded-lg">
              <DollarSign className="w-5 h-5 text-blue-400" />
            </div>
            <span className="text-xs font-medium text-green-400 bg-green-400/10 px-2 py-1 rounded-full flex items-center gap-1">
              <TrendingUp className="w-3 h-3" /> +12%
            </span>
          </div>
          <p className="text-sm text-gray-400 font-medium mb-1">Total Revenue</p>
          <h3 className="text-2xl font-bold text-white tracking-tight">{formatCurrency(kpis.totalRevenue)}</h3>
        </div>

        {/* KPI 2 */}
        <div className="bg-[#13131a] border border-gray-800/60 rounded-2xl p-5 shadow-lg relative overflow-hidden group">
          <div className="absolute inset-0 bg-gradient-to-br from-purple-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
          <div className="flex justify-between items-start mb-4">
            <div className="p-2 bg-purple-500/10 rounded-lg">
              <Activity className="w-5 h-5 text-purple-400" />
            </div>
            <span className="text-xs font-medium text-gray-400 bg-gray-800 px-2 py-1 rounded-full">
              Live
            </span>
          </div>
          <p className="text-sm text-gray-400 font-medium mb-1">Pipeline Value</p>
          <h3 className="text-2xl font-bold text-white tracking-tight">{formatCurrency(kpis.pipelineValue)}</h3>
        </div>

        {/* KPI 3 */}
        <div className="bg-[#13131a] border border-gray-800/60 rounded-2xl p-5 shadow-lg relative overflow-hidden group">
          <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
          <div className="flex justify-between items-start mb-4">
            <div className="p-2 bg-emerald-500/10 rounded-lg">
              <TrendingUp className="w-5 h-5 text-emerald-400" />
            </div>
            <span className="text-xs font-medium text-emerald-400 bg-emerald-400/10 px-2 py-1 rounded-full flex items-center gap-1">
              Stable
            </span>
          </div>
          <p className="text-sm text-gray-400 font-medium mb-1">AI Lead Velocity</p>
          <h3 className="text-2xl font-bold text-white tracking-tight">{kpis.leadVelocity} <span className="text-sm font-normal text-gray-500">/ day</span></h3>
        </div>

        {/* KPI 4 */}
        <div className="bg-[#13131a] border border-gray-800/60 rounded-2xl p-5 shadow-lg relative overflow-hidden group">
          <div className="absolute inset-0 bg-gradient-to-br from-orange-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
          <div className="flex justify-between items-start mb-4">
            <div className="p-2 bg-orange-500/10 rounded-lg">
              <Users className="w-5 h-5 text-orange-400" />
            </div>
          </div>
          <p className="text-sm text-gray-400 font-medium mb-1">Active Agents</p>
          <h3 className="text-2xl font-bold text-white tracking-tight">{kpis.activeAgents}</h3>
        </div>
      </div>

      {/* MIDDLE SECTION: Chart & AI Insights */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Chart */}
        <div className="lg:col-span-2 bg-[#13131a] border border-gray-800/60 rounded-2xl p-6 shadow-lg">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3 className="text-lg font-semibold text-white">Revenue Forecast vs Actual</h3>
              <p className="text-sm text-gray-400 mt-1">AI predicted trajectory based on current pipeline.</p>
            </div>
            {forecast && (
              <div className="text-right hidden sm:block">
                <p className="text-xs text-gray-400 uppercase font-semibold tracking-wider">Projected EOM</p>
                <p className="text-lg font-bold text-blue-400">{formatCurrency(forecast.projected_revenue)}</p>
              </div>
            )}
          </div>
          
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={mockChartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorActual" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                  </linearGradient>
                  <linearGradient id="colorForecast" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis dataKey="name" stroke="#52525b" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis stroke="#52525b" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(value) => `$${value / 1000}k`} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#18181b', borderColor: '#27272a', borderRadius: '8px', color: '#fff' }}
                  itemStyle={{ color: '#e4e4e7' }}
                  formatter={(value: any) => formatCurrency(Number(value))}
                />
                <Area type="monotone" dataKey="actual" stroke="#3b82f6" strokeWidth={3} fillOpacity={1} fill="url(#colorActual)" />
                <Area type="monotone" dataKey="forecast" stroke="#8b5cf6" strokeWidth={3} strokeDasharray="5 5" fillOpacity={1} fill="url(#colorForecast)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* AI Key Drivers */}
        <div className="bg-gradient-to-b from-[#1a1a2e] to-[#13131a] border border-blue-900/30 rounded-2xl p-6 shadow-lg flex flex-col">
          <div className="flex items-center gap-2 mb-6">
            <Bot className="w-5 h-5 text-blue-400" />
            <h3 className="text-lg font-semibold text-white">AI Forecast Drivers</h3>
          </div>
          
          {forecast ? (
            <div className="space-y-4 flex-1">
              {forecast.key_drivers.map((driver: any, idx: number) => (
                <div key={idx} className="p-4 rounded-xl bg-blue-950/20 border border-blue-900/40">
                  <p className="text-sm text-blue-100 font-medium leading-relaxed">"{driver.factor}"</p>
                  <div className="mt-3 flex items-center justify-between">
                    <span className="text-xs text-blue-400/70 font-semibold uppercase tracking-wider">Impact Weight</span>
                    <span className="text-xs font-bold text-blue-300">{(driver.impact_weight * 100).toFixed(0)}%</span>
                  </div>
                  <div className="w-full bg-blue-950 rounded-full h-1.5 mt-2">
                    <div className="bg-blue-500 h-1.5 rounded-full" style={{ width: `${driver.impact_weight * 100}%` }}></div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">Loading AI insights...</div>
          )}
          
          <button className="mt-4 w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors shadow-[0_0_15px_rgba(37,99,235,0.2)]">
            Ask CEO AI for Details
          </button>
        </div>
      </div>

      {/* BOTTOM SECTION: Attention Required Alerts */}
      <div>
        <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <BellRing className="w-5 h-5 text-gray-400" />
          Attention Required
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {alerts.map((alert) => (
            <div key={alert.id} className={`p-4 rounded-xl border flex items-start gap-3 ${
              alert.type === 'critical' ? 'bg-red-950/20 border-red-900/50' :
              alert.type === 'warning' ? 'bg-amber-950/20 border-amber-900/50' :
              'bg-blue-950/20 border-blue-900/50'
            }`}>
              <div className="mt-0.5">
                {alert.type === 'critical' && <AlertTriangle className="w-5 h-5 text-red-500" />}
                {alert.type === 'warning' && <AlertTriangle className="w-5 h-5 text-amber-500" />}
                {alert.type === 'info' && <Info className="w-5 h-5 text-blue-500" />}
              </div>
              <div>
                <p className={`text-sm font-medium ${
                  alert.type === 'critical' ? 'text-red-200' :
                  alert.type === 'warning' ? 'text-amber-200' :
                  'text-blue-200'
                }`}>
                  {alert.message}
                </p>
                <p className="text-xs mt-1.5 text-gray-500">{alert.timestamp}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}
