'use client';

import React, { useRef, useEffect } from 'react';
import ForceGraph2D from 'react-force-graph-2d';

type GraphNode = {
  id?: string | number;
  label?: string;
  color?: string;
  val?: number;
  x?: number;
  y?: number;
  properties?: Record<string, unknown>;
};

type GraphEdge = {
  source?: string | number;
  target?: string | number;
  properties?: { strength?: number };
};

interface GraphWrapperProps {
  data: { nodes: GraphNode[]; edges: GraphEdge[] };
  onNodeClick: (node: GraphNode) => void;
}

export default function GraphWrapper({ data, onNodeClick }: GraphWrapperProps) {
  // ForceGraph2D ref is untyped upstream
  const fgRef = useRef<{
    zoomToFit: (ms: number, pad: number) => void;
    centerAt: (x?: number, y?: number, ms?: number) => void;
    zoom: (k: number, ms: number) => void;
  } | null>(null);

  useEffect(() => {
    if (fgRef.current) {
      setTimeout(() => {
        fgRef.current?.zoomToFit(400, 50);
      }, 100);
    }
  }, [data]);

  return (
    <div className="w-full h-full bg-[#0a0a0a]">
      <ForceGraph2D
        ref={fgRef}
        graphData={{ nodes: data.nodes, links: data.edges }}
        nodeLabel={(node: GraphNode) =>
          `${node.label}: ${String(node.properties?.name || node.properties?.unit_number || node.properties?.type || '')}`
        }
        nodeColor={(node: GraphNode) => node.color || '#64748b'}
        nodeVal={(node: GraphNode) => node.val || 10}
        linkColor={() => 'rgba(255,255,255,0.1)'}
        linkWidth={1.5}
        linkDirectionalParticles={2}
        linkDirectionalParticleSpeed={(d: GraphEdge) =>
          d.properties?.strength ? d.properties.strength * 0.01 : 0.005
        }
        onNodeClick={(node: GraphNode) => {
          fgRef.current?.centerAt(node.x, node.y, 1000);
          fgRef.current?.zoom(8, 2000);
          onNodeClick(node);
        }}
        cooldownTicks={100}
        onEngineStop={() => fgRef.current?.zoomToFit(400, 50)}
      />
    </div>
  );
}
