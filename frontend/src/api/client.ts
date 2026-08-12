// Every backend call goes through this file. If the API contract changes,
// this is the only file that should need touching.

import type { OffersResponse, Store, TrackingRule } from "../types";

export const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API chyba ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchStores(): Promise<Store[]> {
  const res = await fetch(`${API_BASE_URL}/api/stores`);
  return handleResponse<Store[]>(res);
}

export async function fetchOffers(
  items: TrackingRule[],
  storeIds: string[],
  includeMissing = false
): Promise<OffersResponse> {
  const params = new URLSearchParams({
    rules: JSON.stringify(items),
    stores: storeIds.join(","),
  });
  if (includeMissing) params.set("include_missing", "1");
  const res = await fetch(`${API_BASE_URL}/api/offers?${params.toString()}`);
  return handleResponse<OffersResponse>(res);
}

export async function fetchPreferences(): Promise<{ tracking_rules: TrackingRule[]; default_stores: string[] }> {
  const res = await fetch(`${API_BASE_URL}/api/preferences`);
  return handleResponse(res as Response);
}

export async function savePreferences(payload: { tracking_rules: TrackingRule[]; default_stores: string[] }) {
  const res = await fetch(`${API_BASE_URL}/api/preferences`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse(res as Response);
}

export async function fetchProductSuggestions(query: string): Promise<string[]> {
  const params = new URLSearchParams({ query });
  const res = await fetch(`${API_BASE_URL}/api/product-suggestions?${params.toString()}`);
  return handleResponse<string[]>(res);
}
