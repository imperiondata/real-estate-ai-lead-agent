'use client';

import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Bot, User, Send, Loader2, Database, BarChart3 } from 'lucide-react';
import { simulateSSEStream, ChatMessage } from '@/lib/api/mockChatService';

export default function AIChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: '1', role: 'assistant', content: 'Hello Founder. I am online and connected to the Knowledge Graph and Forecast Engine. How can I assist you today?' }
  ]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim()) return;
    
    const userMessage: ChatMessage = { id: Date.now().toString(), role: 'user', content: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsTyping(true);

    // Placeholder for AI response
    const assistantId = (Date.now() + 1).toString();
    setMessages(prev => [...prev, { id: assistantId, role: 'assistant', content: '' }]);

    // Stream handler
    const onToken = (token: string) => {
      setMessages(prev => 
        prev.map(msg => msg.id === assistantId ? { ...msg, content: msg.content + token } : msg)
      );
    };

    const onToolCall = (tool: string, status: 'running' | 'completed') => {
      setMessages(prev => 
        prev.map(msg => msg.id === assistantId ? { ...msg, toolCall: { tool, status } } : msg)
      );
    };

    await simulateSSEStream(userMessage.content, onToken, onToolCall);
    setIsTyping(false);
  };

  const renderToolCall = (toolCall: { tool: string; status: 'running' | 'completed' }) => {
    const isRunning = toolCall.status === 'running';
    const Icon = toolCall.tool === 'AnalyticsAgent' ? BarChart3 : Database;
    
    return (
      <div className={`flex items-center gap-2 text-sm font-medium p-3 rounded-lg mb-3 ${isRunning ? 'bg-blue-900/20 text-blue-400 border border-blue-900/50' : 'bg-gray-800/50 text-gray-400 border border-gray-700'}`}>
        {isRunning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Icon className="w-4 h-4" />}
        {isRunning ? `Calling ${toolCall.tool}...` : `${toolCall.tool} Execution Complete`}
      </div>
    );
  };

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] bg-[#0a0a0a] rounded-2xl border border-gray-800 shadow-2xl overflow-hidden max-w-5xl mx-auto">
      
      {/* Header */}
      <div className="p-4 border-b border-gray-800 bg-[#0f0f13] flex items-center gap-3">
        <div className="p-2 bg-blue-600/20 rounded-lg">
          <Bot className="w-5 h-5 text-blue-400" />
        </div>
        <div>
          <h2 className="text-sm font-bold text-white tracking-wide">CEO AI Orchestrator</h2>
          <p className="text-xs text-gray-400">Powered by Gemini 3.1 Flash-Lite</p>
        </div>
      </div>

      {/* Chat Feed */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex gap-4 max-w-3xl ${msg.role === 'user' ? 'ml-auto flex-row-reverse' : 'mr-auto'}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${msg.role === 'user' ? 'bg-indigo-600' : 'bg-blue-600/20 text-blue-400'}`}>
              {msg.role === 'user' ? <User className="w-5 h-5 text-white" /> : <Bot className="w-5 h-5" />}
            </div>
            
            <div className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
              {/* Tool Call State */}
              {msg.role === 'assistant' && msg.toolCall && renderToolCall(msg.toolCall)}
              
              {/* Message Bubble */}
              {msg.content && (
                <div className={`p-4 rounded-2xl ${msg.role === 'user' ? 'bg-indigo-600 text-white rounded-tr-sm' : 'bg-[#15151a] border border-gray-800 text-gray-200 rounded-tl-sm'}`}>
                  <div className="prose prose-invert prose-sm max-w-none">
                    <ReactMarkdown 
                      remarkPlugins={[remarkGfm]}
                    >
                      {msg.content}
                    </ReactMarkdown>
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
        {isTyping && !messages[messages.length - 1]?.toolCall && !messages[messages.length - 1]?.content && (
          <div className="flex gap-4 max-w-3xl mr-auto">
            <div className="w-8 h-8 rounded-full bg-blue-600/20 flex items-center justify-center shrink-0">
              <Bot className="w-5 h-5 text-blue-400" />
            </div>
            <div className="p-4 rounded-2xl bg-[#15151a] border border-gray-800 rounded-tl-sm flex items-center gap-2">
              <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce"></span>
              <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></span>
              <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 border-t border-gray-800 bg-[#0f0f13]">
        <div className="relative flex items-center max-w-4xl mx-auto">
          <input 
            type="text" 
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Ask the CEO AI to query the graph, forecast revenue, or orchestrate agents..."
            className="w-full bg-[#15151a] border border-gray-700 text-white rounded-xl pl-4 pr-12 py-3.5 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-all text-sm"
          />
          <button 
            onClick={handleSend}
            disabled={isTyping || !input.trim()}
            className="absolute right-2 p-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-800 disabled:text-gray-500 text-white rounded-lg transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>

    </div>
  );
}
