'use client';

import React, { useState, useEffect, useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Html, Box, Instance, Instances } from '@react-three/drei';
import { generateMockTwinData, ProjectData, UnitData, TowerData } from '@/lib/api/mockTwinService';
import { Building2, X, Filter, User, DollarSign, Activity } from 'lucide-react';

// --- 3D Unit Component ---
interface UnitMeshProps {
  unit: UnitData;
  position: [number, number, number];
  hideSold: boolean;
  onHover: (unit: UnitData | null, e: any) => void;
  onClick: (unit: UnitData) => void;
  selectedId: string | null;
}

const UnitMesh = ({ unit, position, hideSold, onHover, onClick, selectedId }: UnitMeshProps) => {
  const isSold = unit.status === 'Sold';
  if (hideSold && isSold) return null;

  const color = unit.status === 'Available' ? '#10b981' : unit.status === 'Hold' ? '#f59e0b' : '#ef4444';
  const isSelected = selectedId === unit.id;

  return (
    <mesh 
      position={position}
      onPointerOver={(e) => { e.stopPropagation(); onHover(unit, e); }}
      onPointerOut={(e) => { e.stopPropagation(); onHover(null, e); }}
      onClick={(e) => { e.stopPropagation(); onClick(unit); }}
    >
      <boxGeometry args={[1.8, 0.8, 1.8]} />
      <meshStandardMaterial 
        color={color} 
        emissive={color} 
        emissiveIntensity={isSelected ? 0.8 : (isSold ? 0.1 : 0.4)} 
        transparent 
        opacity={isSold ? 0.4 : (isSelected ? 1 : 0.8)} 
      />
    </mesh>
  );
};

// --- Main Page Component ---
export default function DigitalTwinPage() {
  const [project, setProject] = useState<ProjectData | null>(null);
  const [hoveredUnit, setHoveredUnit] = useState<UnitData | null>(null);
  const [selectedUnit, setSelectedUnit] = useState<UnitData | null>(null);
  const [hideSold, setHideSold] = useState(false);

  useEffect(() => {
    // Load mock 3D data
    setProject(generateMockTwinData());
  }, []);

  const formatCurrency = (val: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(val);

  if (!project) return <div className="h-full flex items-center justify-center text-white">Loading Twin Data...</div>;

  return (
    <div className="relative w-full h-[calc(100vh-4rem)] -m-6 md:-m-8 bg-[#050505] overflow-hidden">
      
      {/* 1. The 3D Canvas */}
      <Canvas camera={{ position: [20, 15, 20], fov: 45 }}>
        <ambientLight intensity={0.4} />
        <directionalLight position={[10, 20, 10]} intensity={1} />
        <OrbitControls makeDefault minPolarAngle={0} maxPolarAngle={Math.PI / 2 - 0.1} minDistance={10} maxDistance={60} />
        
        {/* Render Towers */}
        <group position={[0, -5, 0]}>
          {project.towers.map((tower, tIdx) => {
            // Offset towers along X axis
            const xOffset = tIdx === 0 ? -6 : 6;
            
            return (
              <group key={tower.id} position={[xOffset, 0, 0]}>
                {/* Tower Base */}
                <mesh position={[0, -0.5, 0]}>
                  <boxGeometry args={[5, 1, 5]} />
                  <meshStandardMaterial color="#1a1a1a" />
                </mesh>
                
                {/* Render Floors and Units */}
                {tower.units.map((floor, fIdx) => (
                  <group key={fIdx} position={[0, fIdx * 1, 0]}>
                    {floor.map((unit, uIdx) => {
                      // Position 4 units in a 2x2 grid per floor
                      const px = uIdx % 2 === 0 ? -1 : 1;
                      const pz = uIdx < 2 ? -1 : 1;
                      return (
                        <UnitMesh 
                          key={unit.id}
                          unit={unit}
                          position={[px, 0.5, pz]}
                          hideSold={hideSold}
                          onHover={(u) => setHoveredUnit(u)}
                          onClick={(u) => setSelectedUnit(u)}
                          selectedId={selectedUnit?.id || null}
                        />
                      );
                    })}
                  </group>
                ))}
              </group>
            );
          })}
        </group>
      </Canvas>

      {/* 2. Raycaster 2D Tooltip Overlay */}
      {hoveredUnit && !selectedUnit && (
        <div className="absolute top-6 right-[350px] bg-[#0f0f13]/90 backdrop-blur-md border border-gray-800 rounded-lg p-3 shadow-2xl pointer-events-none z-10 hidden md:block">
          <p className="text-xs font-bold text-white mb-1">Unit {hoveredUnit.unit_number}</p>
          <div className="flex items-center gap-3 text-xs">
            <span className={hoveredUnit.status === 'Available' ? 'text-emerald-400' : hoveredUnit.status === 'Hold' ? 'text-amber-400' : 'text-red-400'}>
              {hoveredUnit.status}
            </span>
            <span className="text-gray-400">|</span>
            <span className="text-gray-300">{formatCurrency(hoveredUnit.price)}</span>
          </div>
        </div>
      )}

      {/* 3. Floating Control Panel */}
      <div className="absolute top-6 left-6 w-64 bg-[#0f0f13]/80 backdrop-blur-xl border border-gray-800 rounded-2xl shadow-2xl overflow-hidden z-10">
        <div className="p-4 border-b border-gray-800 bg-[#15151a]/50 flex items-center gap-2">
          <Building2 className="w-5 h-5 text-indigo-400" />
          <div>
            <h2 className="text-sm font-bold text-white uppercase tracking-wide">Digital Twin</h2>
            <p className="text-xs text-gray-500">{project.name}</p>
          </div>
        </div>
        
        <div className="p-5">
          <label className="flex items-center justify-between cursor-pointer group mb-4">
            <span className="text-sm font-medium text-gray-300 group-hover:text-white transition-colors">Hide Sold Units</span>
            <input 
              type="checkbox" 
              checked={hideSold}
              onChange={(e) => setHideSold(e.target.checked)}
              className="w-4 h-4 rounded bg-gray-900 border-gray-700 text-indigo-500 focus:ring-indigo-500 focus:ring-offset-gray-900"
            />
          </label>
          
          <div className="pt-4 border-t border-gray-800">
            <p className="text-xs text-gray-500 mb-2 font-semibold uppercase">Inventory Status</p>
            <div className="space-y-2 text-xs text-gray-400 font-medium">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded bg-emerald-500/80 border border-emerald-400"></div> Available</div>
                <span>42%</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded bg-amber-500/80 border border-amber-400"></div> On Hold</div>
                <span>21%</span>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2"><div className="w-3 h-3 rounded bg-red-500/80 border border-red-400"></div> Sold</div>
                <span>37%</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 4. Click State Sidebar (Node Details) */}
      <div className={`absolute top-0 right-0 w-80 h-full bg-[#0f0f13]/95 backdrop-blur-2xl border-l border-gray-800 shadow-2xl transition-transform duration-300 ease-in-out z-20 ${selectedUnit ? 'translate-x-0' : 'translate-x-full'}`}>
        {selectedUnit && (
          <div className="flex flex-col h-full">
            <div className="p-6 border-b border-gray-800 flex items-start justify-between">
              <div>
                <span className={`text-xs font-bold uppercase tracking-wider mb-1 inline-block px-2 py-1 rounded-md ${
                  selectedUnit.status === 'Available' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 
                  selectedUnit.status === 'Hold' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' : 
                  'bg-red-500/10 text-red-400 border border-red-500/20'
                }`}>
                  {selectedUnit.status}
                </span>
                <h2 className="text-2xl font-bold text-white mt-1">Unit {selectedUnit.unit_number}</h2>
                <p className="text-sm text-gray-400 mt-1">{selectedUnit.bhk} • Floor {selectedUnit.floor}</p>
              </div>
              <button onClick={() => setSelectedUnit(null)} className="p-1.5 hover:bg-gray-800 rounded-lg text-gray-400 hover:text-white transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 flex-1 overflow-y-auto space-y-6">
              <div className="bg-gray-900/50 p-4 rounded-xl border border-gray-800 flex justify-between items-center">
                <div className="flex items-center gap-3">
                  <DollarSign className="w-5 h-5 text-gray-400" />
                  <span className="text-sm text-gray-300">Base Price</span>
                </div>
                <span className="font-bold text-white">{formatCurrency(selectedUnit.price)}</span>
              </div>

              {selectedUnit.customer && (
                <div className="space-y-3">
                  <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Attached Lead</h3>
                  <div className="bg-gray-900/50 p-4 rounded-xl border border-gray-800">
                    <div className="flex items-center gap-3 mb-3">
                      <div className="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center">
                        <User className="w-4 h-4 text-white" />
                      </div>
                      <div>
                        <p className="text-sm font-bold text-white">{selectedUnit.customer}</p>
                        <p className="text-xs text-gray-400">KYC Verified</p>
                      </div>
                    </div>
                    {selectedUnit.leadScore && (
                      <div className="flex items-center justify-between pt-3 border-t border-gray-800">
                        <span className="text-xs text-gray-400 flex items-center gap-1"><Activity className="w-3 h-3" /> Intent Score</span>
                        <span className="text-xs font-bold text-amber-400">{selectedUnit.leadScore}/100</span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {selectedUnit.status === 'Available' && (
                <button className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-xl transition-colors shadow-[0_0_15px_rgba(79,70,229,0.2)]">
                  Block Unit for Lead
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
