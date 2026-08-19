'use client';

import { useEffect, useRef } from 'react';

type Handlers = {
  onScoredHot?: () => void;
  onTimelineEvent?: () => void;
};

/**
 * SSE bridge for the ego-neighborhood surfaces (sales-copilot, knowledge-graph).
 * Opens `/api/v1/events/stream` (JWT cookie via Next rewrite) and invokes
 * `onScoredHot` on lead.scored / lead.assigned / lead.hot and `onTimelineEvent`
 * on any lead/whatsapp/conversation event, but only when the event belongs to
 * the selected lead. Handlers are kept in a ref so the EventSource survives
 * re-renders and only reconnects when `leadId` changes.
 */
export function useNeighborhoodSse(leadId: string, handlers: Handlers) {
  const handlersRef = useRef(handlers);

  useEffect(() => {
    handlersRef.current = handlers;
  });

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
          handlersRef.current.onScoredHot?.();
        }
        if (t?.startsWith('lead.') || t?.includes('whatsapp') || t === 'conversation.updated') {
          handlersRef.current.onTimelineEvent?.();
        }
      } catch {
        /* ignore parse / ping */
      }
    };
    es.onerror = () => {
      /* browser auto-reconnects */
    };
    return () => es.close();
  }, [leadId]);
}