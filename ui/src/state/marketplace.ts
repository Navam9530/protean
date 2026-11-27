import { create } from "zustand";

/** Where an import lands: a brand-new draft, or merged/appended into an agent of the open draft. */
export type ImportTarget = { kind: "family" } | { kind: "agent"; parentId: string };

interface Marketplace {
  target: ImportTarget | null; // null = drawer closed
  open: (t: ImportTarget) => void;
  close: () => void;
}

export const useMarketplace = create<Marketplace>()((set) => ({
  target: null,
  open: (target) => set({ target }),
  close: () => set({ target: null }),
}));
