// src/lib/api/mockTimelineService.ts

export type TimelineEvent = {
  id: string;
  type: 'whatsapp.sent' | 'whatsapp.received' | 'payment.received' | 'lead.created' | 'site_visit.scheduled' | 'system.alert' | 'ai.insight';
  title: string;
  description: string;
  timestamp: string;
  actor: string;
  amount?: number;
};

export const generateMockTimeline = (): TimelineEvent[] => {
  return [
    {
      id: 'evt_1',
      type: 'ai.insight',
      title: 'AI Suggested Action',
      description: 'Lead engagement dropped 15%. Recommended action: Escalate to Sales Manager.',
      timestamp: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
      actor: 'CEO AI'
    },
    {
      id: 'evt_2',
      type: 'whatsapp.sent',
      title: 'WhatsApp Follow-up Sent',
      description: '"Hi John, checking in to see if you have any questions about the Tower B floorplan..."',
      timestamp: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
      actor: 'Agent Anohita'
    },
    {
      id: 'evt_3',
      type: 'site_visit.scheduled',
      title: 'Site Visit Confirmed',
      description: 'Scheduled for Saturday, 10:00 AM at The Summit site office.',
      timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(),
      actor: 'System'
    },
    {
      id: 'evt_4',
      type: 'payment.received',
      title: 'Booking Amount Received',
      description: 'Payment verified via Stripe. Unit A-402 temporarily blocked.',
      amount: 50000,
      timestamp: new Date(Date.now() - 1000 * 60 * 60 * 24).toISOString(),
      actor: 'FinanceAgent'
    },
    {
      id: 'evt_5',
      type: 'lead.created',
      title: 'New Lead Generated',
      description: 'Captured via Facebook Ads (Campaign: Summer Luxury). Assigned intent score: 85.',
      timestamp: new Date(Date.now() - 1000 * 60 * 60 * 72).toISOString(),
      actor: 'Marketing API'
    }
  ];
};
