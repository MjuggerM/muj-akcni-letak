import { useEffect, useState } from "react";

import { fetchOffers } from "../api/client";
import type { Offer, TrackingRule } from "../types";

export function useOffers(trackedItems: TrackingRule[], selectedStores: string[], includeMissing = false) {
  const [offers, setOffers] = useState<Offer[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fetchedAt, setFetchedAt] = useState<string | null>(null);
  // Bumped by refetch() to force the effect below to re-run on demand,
  // e.g. from a manual "refresh" button, without waiting for
  // trackedItems/selectedStores to change.
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (trackedItems.length === 0) {
      setOffers([]);
      setFetchedAt(null);
      setError(null);
      return;
    }

    // An empty store selection means every store checkbox is unchecked.
    // The backend treats an empty `stores` param as "no filter" (see
    // backend/app/main.py's `stores` query description) - firing that
    // request anyway would silently fetch and show every store again,
    // the opposite of what an empty selection visually implies, and a
    // wasted scrape of every tracked item for stores nobody asked for.
    // Treat it the same as "nothing to show" instead.
    if (selectedStores.length === 0) {
      setOffers([]);
      setFetchedAt(null);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchOffers(trackedItems, selectedStores, includeMissing)
      .then((res) => {
        if (cancelled) return;
        // kupiapi has already performed the product search. Do not require
        // the scraped display name to literally contain the search phrase:
        // e.g. "kuřecí maso" can legitimately return "Kuřecí prsní řízky".
        setOffers(res.items);
        setFetchedAt(res.fetched_at);
        // Partial scrape failures aren't fatal - surface them, but keep
        // whatever offers did come back.
        setError(res.errors.length > 0 ? res.errors.join("; ") : null);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // includeMissing was previously missing from this array, so toggling
    // "Zobrazit i sledované položky mimo akci" changed state but never
    // actually re-fetched - the checkbox looked like it did nothing until
    // some other dependency happened to change too.
  }, [trackedItems, selectedStores, includeMissing, refreshKey]);

  function refetch() {
    setRefreshKey((k) => k + 1);
  }

  return { offers, loading, error, fetchedAt, refetch };
}