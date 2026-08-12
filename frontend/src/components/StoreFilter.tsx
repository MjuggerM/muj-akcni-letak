import { Store as StoreIconLucide } from "lucide-react";

import type { Store } from "../types";
import { storeColor } from "./StoreIcon";

interface StoreFilterProps {
  stores: Store[];
  selectedStores: string[];
  onToggle: (id: string) => void;
}

export function StoreFilter({ stores, selectedStores, onToggle }: StoreFilterProps) {
  return (
    <div className="rounded-2xl border border-stone-800 bg-stone-900/80 p-4 shadow-lg shadow-black/20">
      <h2 className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-stone-300">
        <StoreIconLucide className="h-3.5 w-3.5" /> Obchody
      </h2>

      {stores.length === 0 ? (
        <p className="text-sm text-stone-400">Načítám seznam obchodů…</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {stores.map((store) => {
            const active = selectedStores.includes(store.id);
            const color = storeColor(store.id);
            return (
              <button
                type="button"
                key={store.id}
                onClick={() => onToggle(store.id)}
                aria-pressed={active}
                className="rounded-full border-2 px-3 py-1.5 text-sm font-semibold transition focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                style={
                  active
                    ? { borderColor: color, backgroundColor: color, color: "#fff" }
                    : { borderColor: "#3f3f46", color: "#f5f5f5", backgroundColor: "#18181b" }
                }
              >
                {store.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
