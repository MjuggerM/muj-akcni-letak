// Mirrors backend/app/schemas.py - keep these two in sync by hand for now.

export interface Store {
  id: string;
  label: string;
}

export type TrackingMatchMode = "broad" | "exact";

export interface TrackingRule {
  id: string;
  query: string;
  label: string;
  match_mode: TrackingMatchMode;
  exact_product_name: string | null;
  excluded_terms: string[];
  visual_key: string | null;
}

export interface Offer {
  product_name: string | null;
  ean?: string | null;
  shop_raw: string;
  store_id: string | null;
  price: string | null;
  amount: string | null;
  validity: string | null;
  tracked_item: { keyword: string; label?: string; excluded_terms: string[]; temporary: boolean } | string;
  tracking_rule_id: string | null;
  visual_key: string | null;
  image_url: string | null;
  unit_price: number | null;
  unit: string | null;
  unit_price_label: string | null;
  is_best_deal: boolean;
  saving_vs_next_percent: number | null;
  historical_best_unit_price: number | null;
  is_historical_best: boolean;
  better_deal: BetterDeal | null;
  on_sale?: boolean;
  temporary?: boolean;
}

export interface BetterDeal {
  shop_name: string;
  price: string | null;
  amount: string | null;
  unit_price_label: string | null;
}

export interface StoreSummary {
  id: string | null;
  label: string;
  offer_count: number;
  coverage_count: number;
  best_deal_count: number;
  recommendation_score: number;
  is_recommended: boolean;
}

export interface OffersResponse {
    items: Offer[];
    store_summaries: StoreSummary[];
    top_hits: Offer[];
    fetched_at: string;
  errors: string[];
}
