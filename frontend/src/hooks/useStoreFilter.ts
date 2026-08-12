import { useEffect, useState } from "react";

const STORAGE_KEY = "muj-akcni-letak:selected-stores";

// Matches the store IDs in backend/app/config.py. Used only until the
// real store list loads from /api/stores on first render.
const DEFAULT_STORES = ["lidl", "penny", "billa", "albert"];

function loadInitial(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as string[]) : DEFAULT_STORES;
  } catch {
    return DEFAULT_STORES;
  }
}

export function useStoreFilter() {
  const [selectedStores, setSelectedStores] = useState<string[]>(loadInitial);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(selectedStores));
  }, [selectedStores]);

  function toggleStore(id: string) {
    setSelectedStores((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]
    );
  }

  return { selectedStores, toggleStore };
}
