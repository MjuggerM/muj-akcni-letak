import { useEffect, useState } from "react";
import type { TrackingRule } from "../types";
import { addRuleExclusion, fetchPreferences, removeRuleExclusion } from "../api/client";
import { findVisualKey } from "../visuals";

const STORAGE_KEY = "muj-akcni-letak:tracked-items";
export const MAX_TRACKED_ITEMS = 50;

function normalizeExclusion(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("cs-CZ").trim();
}

function makeId() {
  return globalThis.crypto?.randomUUID?.() ?? `rule-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function createBroadRule(query: string, excludedTerms: string[] = [], excludedProducts: string[] = []): TrackingRule {
  const trimmed = query.trim();
  return {
    id: makeId(),
    query: trimmed,
    label: trimmed,
    match_mode: "smart",
    exact_product_name: null,
    excluded_terms: excludedTerms,
    excluded_products: excludedProducts,
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
      const legacyBlacklist = (item as { blacklist?: unknown }).blacklist;
      if (!rule.id || !rule.query || !rule.label) return [];
      const excludedTerms = [
        ...(Array.isArray(rule.excluded_terms) ? rule.excluded_terms : []),
        ...(Array.isArray(legacyBlacklist) ? legacyBlacklist.filter((term): term is string => typeof term === "string") : []),
      ].filter((term): term is string => typeof term === "string");
      return [{
        id: rule.id,
        query: rule.query,
        label: rule.label,
        match_mode: rule.match_mode === "exact" ? "exact" : "smart",
        exact_product_name: rule.exact_product_name ?? null,
        excluded_terms: [...new Set(excludedTerms)],
        excluded_products: Array.isArray(rule.excluded_products) ? rule.excluded_products.filter((name): name is string => typeof name === "string") : [],
        visual_key: rule.visual_key ?? findVisualKey(rule.query),
      }];
    });
  } catch {
    return [];
  }
}

function mergeRules(serverRules: TrackingRule[], localRules: TrackingRule[]): TrackingRule[] {
  const merged = new Map<string, TrackingRule>();
  const identity = (rule: TrackingRule) => JSON.stringify([
    rule.match_mode,
    rule.query.toLocaleLowerCase("cs-CZ"),
    rule.exact_product_name,
    rule.excluded_terms,
    rule.excluded_products,
  ]);

  for (const rule of serverRules) merged.set(identity(rule), rule);
  for (const rule of localRules) {
    if (!merged.has(identity(rule))) merged.set(identity(rule), rule);
  }
  return [...merged.values()].slice(0, MAX_TRACKED_ITEMS);
}

export function useTrackedItems() {
  const [trackedItems, setTrackedItems] = useState<TrackingRule[]>(loadInitial);
  const [preferencesLoading, setPreferencesLoading] = useState(true);
  const [preferencesError, setPreferencesError] = useState<string | null>(null);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trackedItems));
  }, [trackedItems]);

  // Prefer saved server values while preserving local-only values if the server has none.
  useEffect(() => {
    let cancelled = false;
    fetchPreferences()
      .then((data) => {
        if (cancelled) return;
        const rules = Array.isArray(data.tracking_rules) ? data.tracking_rules : [];
        if (rules.length > 0) setTrackedItems(mergeRules(rules, trackedItems));
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

  function canAdd(rule: TrackingRule) {
    if (!rule.query || trackedItems.length >= MAX_TRACKED_ITEMS) return false;
    return !trackedItems.some((item) =>
      item.match_mode === rule.match_mode
      && item.query.toLocaleLowerCase("cs-CZ") === rule.query.toLocaleLowerCase("cs-CZ")
      && item.exact_product_name === rule.exact_product_name
      && item.excluded_terms.join("|") === rule.excluded_terms.join("|")
      && item.excluded_products.join("|") === rule.excluded_products.join("|")
    );
  }

  function addBroadItem(name: string, excludedTerms: string[], excludedProducts: string[] = []) {
    const rule = createBroadRule(name, excludedTerms, excludedProducts);
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
      excluded_products: [],
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

  function updateExcludedProducts(id: string, excludedProducts: string[]) {
    setTrackedItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, excluded_products: excludedProducts } : item))
    );
  }

  async function addExclusion(id: string, type: "term" | "product", value: string) {
    try {
      const result = await addRuleExclusion(id, type, value);
      setTrackedItems((previous) => previous.map((item) => item.id === id ? result.tracking_rule : item));
    } catch (err) {
      // Newly added rules live in local state until the user saves settings.
      // Keep the exclusion usable in that state; the Settings save button then
      // persists both the rule and its new exclusion together.
      if (!(err instanceof Error) || !err.message.startsWith("API chyba 404:")) throw err;
      setTrackedItems((previous) => previous.map((item) => {
        if (item.id !== id) return item;
        const key = type === "term" ? "excluded_terms" : "excluded_products";
        const values = item[key];
        return values.some((entry) => normalizeExclusion(entry) === normalizeExclusion(value))
          ? item
          : { ...item, [key]: [...values, value] };
      }));
    }
  }

  async function removeExclusion(id: string, type: "term" | "product", value: string) {
    try {
      const result = await removeRuleExclusion(id, type, value);
      setTrackedItems((previous) => previous.map((item) => item.id === id ? result.tracking_rule : item));
    } catch (err) {
      // Session-only rules are not stored by the backend; update their local copy instead.
      if (!(err instanceof Error) || !err.message.startsWith("API chyba 404:")) throw err;
      setTrackedItems((previous) => previous.map((item) => {
        if (item.id !== id) return item;
        const key = type === "term" ? "excluded_terms" : "excluded_products";
        return {
          ...item,
          [key]: item[key].filter((entry) => normalizeExclusion(entry) !== normalizeExclusion(value)),
        };
      }));
    }
  }

  return {
    trackedItems,
    preferencesLoading,
    preferencesError,
    addBroadItem,
    addExactItem,
    removeItem,
    updateExcludedTerms,
    updateExcludedProducts,
    addExclusion,
    removeExclusion,
    maxTrackedItems: MAX_TRACKED_ITEMS,
  };
}
