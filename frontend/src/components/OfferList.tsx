import type { Offer, StoreSummary } from "../types";
import { ProductVisual } from "./ProductVisual";
import { storeColor } from "./StoreIcon";

interface OfferListProps {
  offers: Offer[];
  storeSummaries: StoreSummary[];
  loading: boolean;
  error: string | null;
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-stone-700 bg-stone-900/60 px-6 py-10 text-center">
      <p className="text-sm text-stone-300">{message}</p>
    </div>
  );
}

export function OfferList({ offers, storeSummaries, loading, error }: OfferListProps) {
  if (loading) {
    return <EmptyState message="Načítám aktuální akce…" />;
  }

  const groups = new Map<string, { label: string; storeId: string | null; offers: Offer[] }>();

  for (const offer of offers) {
    const key = offer.store_id ?? `raw:${offer.shop_raw}`;
    const group = groups.get(key) ?? {
      label: offer.shop_raw,
      storeId: offer.store_id,
      offers: [],
    };
    group.offers.push(offer);
    groups.set(key, group);
  }

  const orderedGroups = [
    ...storeSummaries.flatMap((summary) => {
      const key = summary.id ?? `raw:${summary.label}`;
      const group = groups.get(key);
      return group ? [{ ...group, label: summary.label || group.label, summary }] : [];
    }),
    ...[...groups.entries()]
      .filter(([key]) => !storeSummaries.some((summary) => (summary.id ?? `raw:${summary.label}`) === key))
      .map(([, group]) => ({ ...group, summary: undefined })),
  ];

  return (
    <div className="space-y-5">
      {error && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          Některé nabídky se nepodařilo načíst: {error}
        </div>
      )}

      {offers.length === 0 ? (
        <EmptyState message="Žádné akce na sledované položky ve vybraných obchodech." />
      ) : (
        orderedGroups.map((group) => (
          <section key={group.storeId ?? `raw:${group.label}`}>
            <div className="mb-2 flex items-center gap-2 px-1">
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: storeColor(group.storeId) }} />
              <h3 className="text-sm font-bold uppercase tracking-wide text-stone-300">{group.summary?.label ?? group.label}</h3>
            </div>

            <div className="space-y-2">
              {group.offers.map((offer) => {
                const trackedKey = typeof offer.tracked_item === "string" ? offer.tracked_item : offer.tracked_item?.label ?? offer.tracked_item?.keyword ?? "";
                const isBest = offer.is_best_deal && offer.unit_price != null;
                const productName = offer.product_name ?? trackedKey ?? "Produkt";

                return (
                  <article
                    key={`${offer.tracking_rule_id ?? trackedKey}-${offer.store_id ?? offer.shop_raw}-${offer.visual_key ?? "novisual"}-${productName}-${offer.price ?? "noprice"}-${offer.amount ?? "noamount"}-${offer.validity ?? "novalid"}`}
                    className="relative rounded-xl bg-stone-900/80 p-3 transition-colors hover:bg-stone-900"
                  >
                    {isBest && (
                      <span className="absolute right-3 top-3 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.18em] text-emerald-300">
                        Nejlevnější
                      </span>
                    )}

                    <div className="flex items-start gap-3 pr-20">
                      <ProductVisual imageUrl={offer.image_url} tag={trackedKey} visualKey={offer.visual_key} ean={offer.ean} productName={productName} size="hit" />

                      <div className="min-w-0 flex-1">
                        <p
                          className="text-sm font-semibold text-stone-100"
                          style={{
                            display: "-webkit-box",
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: "vertical",
                            overflow: "hidden",
                          }}
                        >
                          {productName}
                        </p>

                        <div className="mt-2 flex flex-wrap items-baseline gap-2">
                          <span className="text-2xl font-black tracking-tight text-white">{offer.price ?? "Cena neuvedena"}</span>
                          {offer.unit_price_label && (
                            <span className="text-xs text-stone-400">{offer.unit_price_label}</span>
                          )}
                        </div>

                        {offer.amount && (
                          <p className="mt-1 text-xs text-stone-400">{offer.amount}</p>
                        )}
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
