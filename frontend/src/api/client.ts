// Every backend call goes through this file. If the API contract changes,
// this is the only file that should need touching.

import type { OffersResponse, ProductPreview, Store, TrackingRule } from "../types";

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
  return handleResponse<{ tracking_rules: TrackingRule[]; default_stores: string[] }>(res);
}

export async function savePreferences(payload: { tracking_rules: TrackingRule[]; default_stores: string[] }): Promise<{ ok: boolean }> {
  const res = await fetch(`${API_BASE_URL}/api/preferences`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<{ ok: boolean }>(res);
}

export async function fetchProductSuggestions(query: string): Promise<string[]> {
  const params = new URLSearchParams({ query });
  const res = await fetch(`${API_BASE_URL}/api/product-suggestions?${params.toString()}`);
  return handleResponse<string[]>(res);
}

export async function fetchProductPreview(query: string): Promise<ProductPreview[]> {
  const params = new URLSearchParams({ query });
  const res = await fetch(`${API_BASE_URL}/api/product-preview?${params.toString()}`);
  return handleResponse<ProductPreview[]>(res);
}

export async function addRuleExclusion(
  ruleId: string,
  type: "term" | "product",
  value: string,
): Promise<{ ok: boolean; tracking_rule: TrackingRule }> {
  const res = await fetch(`${API_BASE_URL}/api/rules/${encodeURIComponent(ruleId)}/exclude`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type, value }),
  });
  return handleResponse<{ ok: boolean; tracking_rule: TrackingRule }>(res);
}

export async function removeRuleExclusion(
  ruleId: string,
  type: "term" | "product",
  value: string,
): Promise<{ ok: boolean; tracking_rule: TrackingRule }> {
  const res = await fetch(`${API_BASE_URL}/api/rules/${encodeURIComponent(ruleId)}/exclude`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type, value }),
  });
  return handleResponse<{ ok: boolean; tracking_rule: TrackingRule }>(res);
}

// Fotky produktů. Backend NIKDY nečeká na Open Food Facts: buď rovnou vrátí výsledek z cache,
// nebo "pending" (zařazeno do fronty) a frontend se za `retry_after` sekund zeptá znovu.
export type ImageLookupStatus = "found" | "missing" | "pending" | "error";
export type ImageLookupMode = "legacy" | "quality";

export interface ImageLookupResponse {
  status: ImageLookupStatus;
  image_url: string | null;
  retry_after?: number | null;
}

export async function fetchImageLookup(
  productName: string,
  mode: ImageLookupMode = "legacy",
): Promise<ImageLookupResponse> {
  const params = new URLSearchParams({ query: productName, mode });
  const res = await fetch(`${API_BASE_URL}/api/proxy-image?${params.toString()}`);
  return handleResponse<ImageLookupResponse>(res);
}
