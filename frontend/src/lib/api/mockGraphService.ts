// src/lib/api/mockGraphService.ts

export const generateMockGraph = () => {
  const nodes: any[] = [];
  const edges: any[] = [];
  
  // 1. Projects
  nodes.push({ id: 'PRJ-101', label: 'Project', properties: { name: 'The Summit', location: 'Downtown', completion_status: 'Under Construction' }, val: 50, color: '#3b82f6' }); // Blue
  
  // 2. Towers
  ['Tower A', 'Tower B'].forEach((tName, i) => {
    const tId = `T-${i+1}`;
    nodes.push({ id: tId, label: 'Tower', properties: { name: tName, floors: 30 }, val: 30, color: '#8b5cf6' }); // Purple
    edges.push({ source: 'PRJ-101', target: tId, type: 'HAS_TOWER' });
    
    // 3. Units (5 per tower)
    for (let u = 1; u <= 5; u++) {
      const uId = `U-${i+1}0${u}`;
      const status = Math.random() > 0.5 ? 'Available' : (Math.random() > 0.5 ? 'Hold' : 'Sold');
      const color = status === 'Available' ? '#10b981' : status === 'Hold' ? '#f59e0b' : '#ef4444';
      nodes.push({ id: uId, label: 'Unit', properties: { unit_number: `${tName.charAt(tName.length-1)}-${u}0${u}`, status, price: `$${(Math.random() * 2 + 1).toFixed(1)}M` }, val: 15, color });
      edges.push({ source: tId, target: uId, type: 'HAS_UNIT' });
    }
  });

  // 4. Leads (20 leads)
  const firstNames = ['John', 'Jane', 'Alex', 'Sarah', 'Michael', 'Emma', 'David', 'Olivia', 'James', 'Ava', 'Robert', 'Mia', 'William', 'Isabella', 'Joseph', 'Sophia', 'Thomas', 'Charlotte', 'Charles', 'Amelia'];
  const unitIds = nodes.filter(n => n.label === 'Unit').map(n => n.id);
  
  firstNames.forEach((name, i) => {
    const lId = `L-${100 + i}`;
    const score = Math.floor(Math.random() * 60) + 40; // 40-100
    const temperature = score > 80 ? 'Hot' : score > 60 ? 'Warm' : 'Cold';
    const color = temperature === 'Hot' ? '#ef4444' : temperature === 'Warm' ? '#f59e0b' : '#3b82f6';
    
    nodes.push({ id: lId, label: 'Lead', properties: { name: `${name} ${['Smith', 'Johnson', 'Brown', 'Davis'][i % 4]}`, score, temperature, intent: 'High' }, val: 20, color });
    
    // Connect to a random unit
    const targetUnit = unitIds[Math.floor(Math.random() * unitIds.length)];
    edges.push({ source: lId, target: targetUnit, type: 'INTERESTED_IN', properties: { strength: score / 100 } });
    
    // 5. Communications (2-3 per lead)
    const commCount = Math.floor(Math.random() * 2) + 1;
    for (let c = 0; c < commCount; c++) {
      const cId = `C-${i}-${c}`;
      const type = Math.random() > 0.6 ? 'Call' : (Math.random() > 0.5 ? 'WhatsApp' : 'Email');
      nodes.push({ id: cId, label: 'Communication', properties: { type, direction: 'Inbound', sentiment: Math.random() > 0.5 ? 'Positive' : 'Neutral' }, val: 10, color: '#64748b' }); // Slate
      edges.push({ source: lId, target: cId, type: 'ENGAGED_IN' });
    }
  });

  return { nodes, edges };
};

export const mockGraphResponse = {
  status: "success",
  data: generateMockGraph(),
  ai_summary: "Graph successfully loaded. Showing 50+ semantic relationships including Hot Leads, Under Construction Towers, and recent Communications."
};
