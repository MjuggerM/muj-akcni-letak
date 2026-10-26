// Mirrors backend/app/schemas.py - keep these two in sync by hand for now.

export interface Store {
  id: string;
  label: string;
}

export type TrackingMatchMode = "smart" | "exact";

export interface TrackingRule {
  id: string;
  query: string;
  label: string;
  match_mode: TrackingMatchMode;
  exact_product_name: string | null;
  excluded_terms: string[];
  excluded_products: string[];
  visual_key: string | null;
}

// Mirrors backend/app/schemas.py::TrackedItem.
export interface TrackedItem {
  keyword: string;
  label?: string;
  excluded_terms: string[];
  excluded_products: string[];
  temporary: boolean;
}

export interface Offer {
  product_name: string | null;
  shop_raw: string;
  store_id: string | null;
  price: string | null;
  amount: string | null;
  validity: string | null;
  tracked_item: TrackedItem | string;
  tracking_rule_id: string | null;
  visual_key: string | null;
  image_url: string | null;
  unit_price: number | null;
  unit: string | null;
  unit_price_label: string | null;
  is_best_deal: boolean;
  confidence: "high" | "medium" | "low";
  match_reason: string | null;
  suggested_exclusion_term: string | null;
  on_sale?: boolean;
  temporary?: boolean;
}

export interface ProductPreview {
  product_name: string;
  confidence: "high" | "medium" | "low";
  match_reason: string | null;
  suggested_exclusion_term: string | null;
}

export interface OffersResponse {
  items: Offer[];
  fetched_at: string;
  errors: string[];
}
