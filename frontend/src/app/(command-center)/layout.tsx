'use client';

import React from 'react';
import Link from 'next/link';
import { LayoutDashboard, MessageSquare, Box, Network, Bot } from 'lucide-react';
import { usePathname } from 'next/navigation';

export default function CommandCenterLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  const navigation = [
    { name: 'Executive Dashboard', href: '/dashboard-mvp', icon: LayoutDashboard },
    { name: 'CEO AI Chat', href: '/ai-chat', icon: MessageSquare },
    { name: 'Digital Twin', href: '/digital-twin', icon: Box },
    { name: 'Knowledge Graph', href: '/knowledge-graph', icon: Network },
    { name: 'Sales Copilot', href: '/sales-copilot', icon: Bot },
  ];

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white flex">
      {/* Sidebar */}
      <div className="w-64 border-r border-gray-800 bg-[#0f0f13] flex flex-col hidden md:flex">
        <div className="p-6 border-b border-gray-800">
          <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-indigo-500 tracking-wide">
            IREIOS 3.0
          </h1>
          <p className="text-xs text-gray-500 mt-1 uppercase tracking-widest font-semibold">Command Center</p>
        </div>
        
        <nav className="flex-1 p-4 space-y-1">
          {navigation.map((item) => {
            const isActive = pathname === item.href || (pathname === '/' && item.href === '/dashboard-mvp');
            return (
              <Link
                key={item.name}
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                  isActive 
                    ? 'bg-blue-600/10 text-blue-400 border border-blue-500/20 shadow-[0_0_15px_rgba(37,99,235,0.1)]' 
                    : 'text-gray-400 hover:bg-gray-800/50 hover:text-gray-200'
                }`}
              >
                <item.icon className={`w-5 h-5 ${isActive ? 'text-blue-400' : 'text-gray-500'}`} />
                {item.name}
              </Link>
            )
          })}
        </nav>

        <div className="p-4 border-t border-gray-800">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-blue-600 to-purple-600 flex items-center justify-center text-xs font-bold text-white shadow-lg shadow-purple-500/20">
              FD
            </div>
            <div>
              <p className="text-sm font-medium text-gray-200">Founder</p>
              <p className="text-xs text-gray-500">System Admin</p>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="h-16 border-b border-gray-800 bg-[#0f0f13]/80 backdrop-blur-md flex items-center justify-between px-6 sticky top-0 z-20">
          <div className="flex items-center gap-4">
            <h2 className="text-lg font-semibold text-gray-100">
              {navigation.find(n => pathname === n.href || (pathname === '/' && n.href === '/dashboard-mvp'))?.name || 'Executive Dashboard'}
            </h2>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 px-3 py-1.5 bg-green-500/10 border border-green-500/20 rounded-full">
              <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse"></div>
              <span className="text-xs font-medium text-green-400">AI Engine Online</span>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-auto p-6 md:p-8">
          {children}
        </main>
      </div>
    </div>
  );
}
