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
  }, [trackedItems, selectedStores, refreshKey]);

  function refetch() {
    setRefreshKey((k) => k + 1);
  }

  return { offers, loading, error, fetchedAt, refetch };
}
