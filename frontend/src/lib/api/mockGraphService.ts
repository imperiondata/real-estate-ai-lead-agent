// src/lib/api/mockGraphService.ts
// IREIOS 4.0 Day-1 mock — ego neighborhood shape (matches GET /graph/neighborhood)

export type EgoNode = {
  id: string;
  label: 'Lead' | 'Agent';
  properties: Record<string, string | number>;
  val: number;
  color: string;
};

export type EgoEdge = {
  source: string;
  target: string;
  type: 'ASSIGNED_TO' | 'SIMILAR_TO';
  properties: Record<string, number | string>;
};

const TEMP_COLORS: Record<string, string> = {
  Hot: '#ef4444',
  Warm: '#f59e0b',
  Cold: '#3b82f6',
};
const AGENT_COLOR = '#8b5cf6';

/** Ego graph: center lead + assigned agent + similar leads (not full Project/Tower storm). */
export const generateMockEgoGraph = (leadId = 123) => {
  const nodes: EgoNode[] = [];
  const edges: EgoEdge[] = [];

  nodes.push({
    id: `lead:${leadId}`,
    label: 'Lead',
    properties: { name: 'Priya Sharma', score: 82, temperature: 'Hot', lead_id: leadId },
    val: 24,
    color: TEMP_COLORS.Hot,
  });

  nodes.push({
    id: 'agent:Jane',
    label: 'Agent',
    properties: { name: 'Jane' },
    val: 18,
    color: AGENT_COLOR,
  });
  edges.push({
    source: `lead:${leadId}`,
    target: 'agent:Jane',
    type: 'ASSIGNED_TO',
    properties: {},
  });

  const similars = [
    { id: 456, name: 'Arjun Mehta', score: 60, temperature: 'Warm' as const },
    { id: 789, name: 'Neha Kapoor', score: 44, temperature: 'Cold' as const },
    { id: 321, name: 'Rohan Das', score: 71, temperature: 'Hot' as const },
  ];

  for (const s of similars) {
    nodes.push({
      id: `lead:${s.id}`,
      label: 'Lead',
      properties: {
        name: s.name,
        score: s.score,
        temperature: s.temperature,
        lead_id: s.id,
      },
      val: 16,
      color: TEMP_COLORS[s.temperature],
    });
    edges.push({
      source: `lead:${leadId}`,
      target: `lead:${s.id}`,
      type: 'SIMILAR_TO',
      properties: { strength: 0.72 },
    });
  }

  return { nodes, edges };
};

/** @deprecated use generateMockEgoGraph — kept as alias for older imports */
export const generateMockGraph = generateMockEgoGraph;

export const mockGraphResponse = {
  status: 'success',
  available: true,
  lead_id: 123,
  data: generateMockEgoGraph(123),
  ai_summary: 'Ego network: center lead, assigned agent, and similar leads.',
};
