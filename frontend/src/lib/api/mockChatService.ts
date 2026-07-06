// src/lib/api/mockChatService.ts

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolCall?: { tool: string; status: 'running' | 'completed' };
};

export const simulateSSEStream = async (
  query: string, 
  onToken: (token: string) => void, 
  onToolCall: (tool: string, status: 'running' | 'completed') => void
) => {
  // Simulate network latency
  await new Promise(resolve => setTimeout(resolve, 500));

  if (query.toLowerCase().includes('forecast') || query.toLowerCase().includes('revenue')) {
    onToolCall('AnalyticsAgent', 'running');
    await new Promise(resolve => setTimeout(resolve, 1500));
    onToolCall('AnalyticsAgent', 'completed');
    
    const responseText = "Based on the current pipeline, the projected revenue for this month is **$4.2M**.\n\nKey drivers include:\n- High volume of Site Visits in Week 2\n- 3 bulk deals currently in advanced negotiation.";
    
    // Simulate token-by-token streaming
    const words = responseText.split(' ');
    for (let i = 0; i < words.length; i++) {
      onToken(words[i] + ' ');
      await new Promise(resolve => setTimeout(resolve, Math.random() * 50 + 20));
    }
  } else if (query.toLowerCase().includes('graph') || query.toLowerCase().includes('lead')) {
    onToolCall('Neo4jGraph', 'running');
    await new Promise(resolve => setTimeout(resolve, 1200));
    onToolCall('Neo4jGraph', 'completed');
    
    const responseText = "I found **14 Hot Leads** actively looking at *Tower B*. I recommend escalating these to the Sales Manager immediately to lock in the deals.";
    
    const words = responseText.split(' ');
    for (let i = 0; i < words.length; i++) {
      onToken(words[i] + ' ');
      await new Promise(resolve => setTimeout(resolve, Math.random() * 50 + 20));
    }
  } else {
    const responseText = "I can help with that. Could you provide a bit more context on what specific data you need from the Knowledge Graph or Forecast Engine?";
    const words = responseText.split(' ');
    for (let i = 0; i < words.length; i++) {
      onToken(words[i] + ' ');
      await new Promise(resolve => setTimeout(resolve, Math.random() * 50 + 20));
    }
  }
};
