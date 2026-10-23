"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type { RangeKey } from "./api/types";
import { DEFAULT_RANGE, isRangeKey } from "./range";

/**
 * Persisted UI preferences only (never server data). Rehydrated after mount so the
 * first client render matches the server render. The theme itself is persisted by
 * next-themes.
 */
interface UiPrefs {
  range: RangeKey;
  sidebarCollapsed: boolean;
  autoRefresh: boolean;
  setRange: (range: RangeKey) => void;
  toggleSidebar: () => void;
  setAutoRefresh: (value: boolean) => void;
}

export const useUiPrefs = create<UiPrefs>()(
  persist(
    (set) => ({
      range: DEFAULT_RANGE,
      sidebarCollapsed: false,
      autoRefresh: true,
      setRange: (range) => set({ range }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setAutoRefresh: (autoRefresh) => set({ autoRefresh }),
    }),
    {
      name: "tokenshield.ui",
      version: 1,
      skipHydration: true,
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ range: s.range, sidebarCollapsed: s.sidebarCollapsed, autoRefresh: s.autoRefresh }),
      merge: (persisted, current) => {
        const p = (persisted ?? {}) as Partial<UiPrefs>;
        return {
          ...current,
          range: isRangeKey(p.range) ? p.range : current.range,
          sidebarCollapsed: typeof p.sidebarCollapsed === "boolean" ? p.sidebarCollapsed : current.sidebarCollapsed,
          autoRefresh: typeof p.autoRefresh === "boolean" ? p.autoRefresh : current.autoRefresh,
        };
      },
    },
  ),
);
