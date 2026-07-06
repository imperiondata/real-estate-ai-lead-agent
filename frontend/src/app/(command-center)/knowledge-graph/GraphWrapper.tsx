'use client';

import React, { useRef, useEffect, useCallback } from 'react';
import ForceGraph2D from 'react-force-graph-2d';

interface GraphWrapperProps {
  data: { nodes: any[]; edges: any[] };
  onNodeClick: (node: any) => void;
}

export default function GraphWrapper({ data, onNodeClick }: GraphWrapperProps) {
  const fgRef = useRef<any>();

  // Optional: Auto-fit graph on load
  useEffect(() => {
    if (fgRef.current) {
      setTimeout(() => {
        fgRef.current.zoomToFit(400, 50);
      }, 100);
    }
  }, [data]);

  return (
    <div className="w-full h-full bg-[#0a0a0a]">
      <ForceGraph2D
        ref={fgRef}
        graphData={{ nodes: data.nodes, links: data.edges }}
        nodeLabel={(node: any) => `${node.label}: ${node.properties?.name || node.properties?.unit_number || node.properties?.type}`}
        nodeColor={(node: any) => node.color}
        nodeVal={(node: any) => node.val}
        linkColor={() => 'rgba(255,255,255,0.1)'}
        linkWidth={1.5}
        linkDirectionalParticles={2}
        linkDirectionalParticleSpeed={d => d.properties?.strength ? d.properties.strength * 0.01 : 0.005}
        onNodeClick={(node) => {
          // Center camera on node
          fgRef.current.centerAt(node.x, node.y, 1000);
          fgRef.current.zoom(8, 2000);
          onNodeClick(node);
        }}
        // Physics configurations to keep it stable
        cooldownTicks={100}
        onEngineStop={() => fgRef.current.zoomToFit(400, 50)}
      />
    </div>
  );
}
