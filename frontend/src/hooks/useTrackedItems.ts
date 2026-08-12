import { useEffect, useState } from "react";
import type { TrackingRule } from "../types";
import { fetchPreferences } from "../api/client";
import { findVisualKey } from "../visuals";

const STORAGE_KEY = "muj-akcni-letak:tracked-items";
export const MAX_TRACKED_ITEMS = 50;

function makeId() {
  return globalThis.crypto?.randomUUID?.() ?? `rule-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function createBroadRule(query: string, excludedTerms: string[] = []): TrackingRule {
  const trimmed = query.trim();
  return {
    id: makeId(),
    query: trimmed,
    label: trimmed,
    match_mode: "broad",
    exact_product_name: null,
    excluded_terms: excludedTerms,
    visual_key: findVisualKey(trimmed),
  };
}

function loadInitial(): TrackingRule[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    // Migrate the former string[] storage shape on the user's first visit.
    return parsed.flatMap((item) => {
      if (typeof item === "string") return [createBroadRule(item)];
      if (!item || typeof item !== "object") return [];
      const rule = item as Partial<TrackingRule>;
      if (!rule.id || !rule.query || !rule.label) return [];
      return [{
        id: rule.id,
        query: rule.query,
        label: rule.label,
        match_mode: rule.match_mode === "exact" ? "exact" : "broad",
        exact_product_name: rule.exact_product_name ?? null,
        excluded_terms: Array.isArray(rule.excluded_terms) ? rule.excluded_terms.filter((term): term is string => typeof term === "string") : [],
        visual_key: rule.visual_key ?? findVisualKey(rule.query),
      }];
    });
  } catch {
    return [];
  }
}

export function useTrackedItems() {
  const [trackedItems, setTrackedItems] = useState<TrackingRule[]>(loadInitial);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trackedItems));
  }, [trackedItems]);

  // On first load, if we don't have local items, try to load server-side preferences.
  useEffect(() => {
    let cancelled = false;
    if (trackedItems.length > 0) return;
    fetchPreferences()
      .then((data) => {
        if (cancelled) return;
        const rules = Array.isArray(data.tracking_rules) ? data.tracking_rules : [];
        if (rules.length > 0) setTrackedItems(rules as TrackingRule[]);
      })
      .catch(() => {})
      .finally(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  function canAdd(rule: TrackingRule) {
    if (!rule.query || trackedItems.length >= MAX_TRACKED_ITEMS) return false;
    return !trackedItems.some((item) =>
      item.match_mode === rule.match_mode
      && item.query.toLocaleLowerCase("cs-CZ") === rule.query.toLocaleLowerCase("cs-CZ")
      && item.exact_product_name === rule.exact_product_name
      && item.excluded_terms.join("|") === rule.excluded_terms.join("|")
    );
  }

  function addBroadItem(name: string, excludedTerms: string[]) {
    const rule = createBroadRule(name, excludedTerms);
    if (!canAdd(rule)) return false;
    setTrackedItems((prev) =>
      [...prev, rule]
    );
    return true;
  }

  function addExactItem(query: string, productName: string) {
    const rule: TrackingRule = {
      id: makeId(),
      query: query.trim(),
      label: productName,
      match_mode: "exact",
      exact_product_name: productName,
      excluded_terms: [],
      visual_key: findVisualKey(query),
    };
    if (!canAdd(rule)) return false;
    setTrackedItems((prev) => [...prev, rule]);
    return true;
  }

  function removeItem(id: string) {
    setTrackedItems((prev) => prev.filter((item) => item.id !== id));
  }

  function updateExcludedTerms(id: string, excludedTerms: string[]) {
    setTrackedItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, excluded_terms: excludedTerms } : item))
    );
  }

  return { trackedItems, addBroadItem, addExactItem, removeItem, updateExcludedTerms, maxTrackedItems: MAX_TRACKED_ITEMS };
}
