import { useEffect, useState } from "react";
import { fetchPreferences } from "../api/client";

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
  const [preferencesLoading, setPreferencesLoading] = useState(true);
  const [preferencesError, setPreferencesError] = useState<string | null>(null);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(selectedStores));
  }, [selectedStores]);

  useEffect(() => {
    let cancelled = false;
    fetchPreferences()
      .then((data) => {
        if (!cancelled && Array.isArray(data.default_stores)) {
          const stores = data.default_stores.filter((id): id is string => typeof id === "string");
          if (stores.length > 0 || selectedStores.length === 0) setSelectedStores(stores);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setPreferencesError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setPreferencesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function toggleStore(id: string) {
    setSelectedStores((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]
    );
  }

  return { selectedStores, toggleStore, preferencesLoading, preferencesError };
}
