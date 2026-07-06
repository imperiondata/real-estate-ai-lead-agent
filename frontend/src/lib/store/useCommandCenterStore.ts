import { create } from 'zustand';

interface CommandCenterState {
  activeProjectId: string | null;
  timeframe: 'weekly' | 'monthly' | 'yearly';
  setActiveProject: (id: string | null) => void;
  setTimeframe: (tf: 'weekly' | 'monthly' | 'yearly') => void;
}

export const useCommandCenterStore = create<CommandCenterState>((set) => ({
  activeProjectId: 'PRJ-101', // Default to PRJ-101 as per architecture plan
  timeframe: 'monthly',
  setActiveProject: (id) => set({ activeProjectId: id }),
  setTimeframe: (tf) => set({ timeframe: tf }),
}));
