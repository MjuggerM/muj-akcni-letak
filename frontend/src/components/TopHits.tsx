import type { Offer } from "../types";
import { ProductVisual } from "./ProductVisual";

interface TopHitsProps {
  allOffers: Offer[];
}

function trackedKeyFor(offer: Offer) {
  return offer.tracking_rule_id ?? (typeof offer.tracked_item === "string" ? offer.tracked_item : offer.tracked_item?.keyword ?? offer.tracked_item?.label ?? "");
}

const STORE_ORDER = ["lidl", "albert", "penny", "billa"];

function storeOrder(storeId: string | null) {
  const index = storeId ? STORE_ORDER.indexOf(storeId) : -1;
  return index === -1 ? STORE_ORDER.length : index;
}

function shopLabel(offer: Offer) {
  return offer.store_id ?? offer.shop_raw;
}

export function TopHits({ allOffers }: TopHitsProps) {
  if (allOffers.length === 0) return null;

  const storeGroups = [...allOffers].sort((a, b) => {
    const storeDiff = storeOrder(a.store_id) - storeOrder(b.store_id);
    if (storeDiff !== 0) return storeDiff;
    const priceDiff = (a.unit_price ?? Number.POSITIVE_INFINITY) - (b.unit_price ?? Number.POSITIVE_INFINITY);
    if (priceDiff !== 0) return priceDiff;
    return (a.product_name ?? "").localeCompare(b.product_name ?? "", "cs-CZ");
  }).reduce<Map<string, Offer[]>>((groups, offer) => {
    const key = shopLabel(offer);
    const current = groups.get(key) ?? [];
    current.push(offer);
    groups.set(key, current);
    return groups;
  }, new Map());

  return (
    <section className="mb-8 rounded-2xl border border-stone-700 bg-stone-900/90 p-4 text-stone-100 shadow-xl shadow-black/20 sm:p-5">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-bold text-stone-100">Nejlepší ceny dnes</h2>
      </div>
      <div className="space-y-4">
        {Array.from(storeGroups.entries()).map(([store, offers]) => (
          <section key={store} className="rounded-2xl bg-stone-800/80 p-3 shadow-sm ring-1 ring-stone-700">
            <div className="mb-3 flex items-center justify-between gap-2 px-1">
              <div>
                <h3 className="text-sm font-bold text-stone-100">{store}</h3>
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {offers.map((offer) => {
                const trackedLabel = typeof offer.tracked_item === "string" ? offer.tracked_item : offer.tracked_item?.label ?? offer.tracked_item?.keyword ?? "";
                const comparison = allOffers
                  .filter((candidate) => trackedKeyFor(candidate) === trackedKeyFor(offer))
                  .filter((candidate) => candidate.price)
                  .slice()
                  .sort((a, b) => (a.unit_price ?? Number.POSITIVE_INFINITY) - (b.unit_price ?? Number.POSITIVE_INFINITY))
                  .reduce<Offer[]>((deduped, candidate) => {
                    const key = (candidate.store_id ?? candidate.shop_raw ?? "unknown").toLowerCase();
                    const existing = deduped.find((item) => ((item.store_id ?? item.shop_raw ?? "unknown").toLowerCase()) === key);
                    if (!existing) {
                      deduped.push(candidate);
                      return deduped;
                    }
                    if ((candidate.unit_price ?? Number.POSITIVE_INFINITY) < (existing.unit_price ?? Number.POSITIVE_INFINITY)) {
                      const idx = deduped.indexOf(existing);
                      deduped[idx] = candidate;
                    }
                    return deduped;
                  }, []);
                const winner = comparison[0] ?? offer;
                const isWinner =
                  (winner.store_id ?? winner.shop_raw ?? "") === (offer.store_id ?? offer.shop_raw ?? "") &&
                  winner.product_name === offer.product_name &&
                  winner.price === offer.price;
                const isBestInStore = offers.reduce((best, candidate) => {
                  if (candidate.unit_price == null) return best;
                  if (best == null || candidate.unit_price < best.unit_price!) return candidate;
                  return best;
                }, null as Offer | null) === offer;
                const uniqueKey = `${trackedLabel}-${offer.shop_raw}-${offer.product_name ?? "unknown"}-${offer.price ?? "unknown"}-${offer.unit_price ?? "unknown"}`;

                return (
                  <article key={uniqueKey} className={`overflow-hidden rounded-2xl bg-stone-900 shadow-sm ring-1 ${isWinner || isBestInStore ? "ring-emerald-500/70" : "ring-stone-700"}`}>
                    <div className="grid gap-3 p-4 sm:grid-cols-[88px_1fr]">
                      <ProductVisual imageUrl={offer.image_url} tag={trackedLabel} visualKey={offer.visual_key} productName={offer.product_name} size="card" />
                      <div className="min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <p className="truncate text-sm font-semibold text-stone-100">{offer.product_name ?? trackedLabel}</p>
                          {(isWinner || isBestInStore) && (
                            <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-300">
                              Nejlevnější
                            </span>
                          )}
                        </div>
                        <p className="mt-1 text-3xl font-black tracking-tight text-white">{offer.price ?? "Cena neuvedena"}</p>
                        <p className="text-xs font-medium text-emerald-300">{offer.unit_price_label ?? offer.amount ?? ""}</p>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}
