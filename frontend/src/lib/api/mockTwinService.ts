// src/lib/api/mockTwinService.ts

export type UnitStatus = 'Available' | 'Hold' | 'Sold';

export interface UnitData {
  id: string;
  unit_number: string;
  status: UnitStatus;
  price: number;
  bhk: string;
  floor: number;
  customer?: string;
  leadScore?: number;
}

export interface TowerData {
  id: string;
  name: string;
  units: UnitData[][]; // 2D array: floors -> units
}

export interface ProjectData {
  id: string;
  name: string;
  towers: TowerData[];
}

export const generateMockTwinData = (): ProjectData => {
  const towers: TowerData[] = [];
  const floorsCount = 10;
  const unitsPerFloor = 4;

  const names = ['John Doe', 'Sarah Connor', 'Michael Smith', 'Emma Johnson', undefined];

  ['Tower A', 'Tower B'].forEach((towerName, tIdx) => {
    const towerId = `T${tIdx + 1}`;
    const floors: UnitData[][] = [];

    for (let f = 1; f <= floorsCount; f++) {
      const floorUnits: UnitData[] = [];
      for (let u = 1; u <= unitsPerFloor; u++) {
        const unitId = `${towerId}-F${f}-U${u}`;
        const unitNum = `${towerName.split(' ')[1]}-${f}0${u}`;
        
        // Randomize status
        const rand = Math.random();
        let status: UnitStatus = 'Available';
        let customer = undefined;
        let leadScore = undefined;

        if (rand > 0.7) {
          status = 'Sold';
          customer = names[Math.floor(Math.random() * (names.length - 1))]; // Pick a name
        } else if (rand > 0.4) {
          status = 'Hold';
          customer = names[Math.floor(Math.random() * (names.length - 1))];
          leadScore = Math.floor(Math.random() * 40) + 60; // 60-100
        }

        const price = Math.floor(Math.random() * 500000) + 800000;
        const bhk = (Math.floor(Math.random() * 3) + 2) + ' BHK';

        floorUnits.push({
          id: unitId,
          unit_number: unitNum,
          status,
          price,
          bhk,
          floor: f,
          customer,
          leadScore
        });
      }
      floors.push(floorUnits);
    }
    
    towers.push({ id: towerId, name: towerName, units: floors });
  });

  return {
    id: 'PRJ-101',
    name: 'The Summit',
    towers
  };
};
