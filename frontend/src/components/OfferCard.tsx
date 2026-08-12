import { Clock } from "lucide-react";

import type { Offer } from "../types";
import { ProductVisual } from "./ProductVisual";

interface OfferCardProps {
  offer: Offer;
}

export function OfferCard({ offer }: OfferCardProps) {
  const betterDealText = [offer.better_deal?.price, offer.better_deal?.amount].filter(Boolean).join(" / ");
  const trackedLabel = typeof offer.tracked_item === "string" ? offer.tracked_item : offer.tracked_item?.label ?? offer.tracked_item?.keyword ?? "";
  const isOnSale = offer.on_sale !== false;

  return (
    <article className={`overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm transition-shadow hover:shadow-md ${isOnSale ? "" : "opacity-70"}`}>
      {offer.better_deal && (
        <div className="border-b border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-snug text-amber-900">
          <span className="font-bold">💡 Tip:</span> V {offer.better_deal.shop_name} mají toto levněji
          {betterDealText && <> ({betterDealText})</>}.
        </div>
      )}
      <div className="p-4">
        <div className="flex gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="min-h-11 font-semibold leading-snug text-stone-900">
              {offer.product_name ?? "(neznámý produkt)"}
              {!isOnSale && <span className="ml-2 inline-block rounded-full bg-stone-100 px-2 py-0.5 text-xs font-semibold text-stone-600">Není v akci</span>}
              {offer.temporary && <span className="ml-2 inline-block rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-semibold text-indigo-700">Dočasné</span>}
            </h3>
            <div className="mt-3 flex items-end justify-between gap-2">
              <span className="text-2xl font-black leading-none tracking-tight text-stone-950">{isOnSale ? (offer.price ?? "neuvedeno") : "—"}</span>
              <span className="text-right text-xs text-stone-500">{offer.amount ?? ""}</span>
            </div>
          </div>
          <ProductVisual imageUrl={offer.image_url} tag={trackedLabel} visualKey={offer.visual_key} productName={offer.product_name} />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-stone-500">
          {offer.unit_price_label && <span className="font-semibold text-emerald-700">{offer.unit_price_label}</span>}
          {offer.validity && <span className="inline-flex items-center gap-1"><Clock className="h-3.5 w-3.5" />{offer.validity}</span>}
          <span className="rounded-full bg-stone-100 px-2 py-0.5 text-stone-500">#{trackedLabel}</span>
        </div>
      </div>
    </article>
  );
}
