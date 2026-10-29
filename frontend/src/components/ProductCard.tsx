import { useCallback, useEffect, useId, useRef, useState, type RefObject } from "react";
import { EyeOff, RotateCcw } from "lucide-react";

import type { ImageLookupMode } from "../api/client";
import type { Offer } from "../types";
import { storeColor } from "./storeColors";
import { ProductVisual } from "./ProductVisual";

export type ExclusionAction = { type: "term" | "product"; value: string };

export function getOfferKey(offer: Offer): string {
  const label = typeof offer.tracked_item === "string"
    ? offer.tracked_item
    : offer.tracked_item.label ?? offer.tracked_item.keyword;

  return JSON.stringify([
    offer.tracking_rule_id,
    label,
    offer.store_id,
    offer.shop_raw,
    offer.product_name,
    offer.price,
    offer.amount,
    offer.unit,
  ]);
}

interface ProductCardProps {
  offer: Offer;
  ruleLabel: string;
  comparedShops: number;
  imageLookupMode: ImageLookupMode;
  excluded: boolean;
  onExclude: (action: ExclusionAction) => Promise<void>;
  onUndoExclude: () => Promise<void>;
}

const STORE_LABELS: Record<string, string> = {
  lidl: "Lidl",
  albert: "Albert",
  penny: "Penny",
  billa: "Billa",
};

function productLabel(offer: Offer, ruleLabel: string) {
  return offer.product_name ?? ruleLabel;
}

function storeLabel(offer: Offer) {
  return (offer.store_id && STORE_LABELS[offer.store_id]) || offer.shop_raw;
}

function parsePrice(raw: string | null) {
  if (!raw) return null;
  const match = raw.replace(/\u00a0/g, " ").trim().match(/^(\d[\d\s]*?)(?:[.,](\d{1,2}))?\s*(Kč|CZK)?$/i);
  if (!match) return null;

  const whole = match[1].replace(/\s+/g, "\u00a0");
  const fraction = match[2];
  return {
    amount: fraction ? `${whole},${fraction.padEnd(2, "0")}` : whole,
    currency: match[3]?.toUpperCase() === "CZK" ? "CZK" : "Kč",
  };
}

function unitPriceLabel(offer: Offer) {
  if (offer.unit_price !== null && offer.unit) {
    return `${offer.unit_price.toLocaleString("cs-CZ", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })} Kč/${offer.unit}`;
  }
  return offer.unit_price_label ?? offer.amount;
}

type DismissReason = "outside" | "escape";

function useDismiss<T extends HTMLElement>(ref: RefObject<T>, active: boolean, onDismiss: (reason: DismissReason) => void) {
  const dismiss = useCallback((event: Event) => {
    if (!ref.current?.contains(event.target as Node)) onDismiss("outside");
  }, [onDismiss, ref]);

  useEffect(() => {
    if (!active) return;
    document.addEventListener("pointerdown", dismiss);
    document.addEventListener("keydown", handleEscape);
    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onDismiss("escape");
    }
    return () => {
      document.removeEventListener("pointerdown", dismiss);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [active, dismiss, onDismiss]);
}

export function ProductCard({
  offer,
  ruleLabel,
  comparedShops,
  imageLookupMode,
  excluded,
  onExclude,
  onUndoExclude,
}: ProductCardProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [tipPinned, setTipPinned] = useState(false);
  const [tipHovered, setTipHovered] = useState(false);
  const [tipFocused, setTipFocused] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tooltipId = useId();
  const menuId = useId();
  const menuRef = useRef<HTMLDivElement>(null);
  const menuTriggerRef = useRef<HTMLButtonElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const label = productLabel(offer, ruleLabel);
  const price = parsePrice(offer.price);
  const unitLabel = offer.on_sale === false ? null : unitPriceLabel(offer);
  const uncertain = offer.confidence === "medium" || offer.confidence === "low";
  const showTooltip = tipPinned || tipHovered || tipFocused;
  const bestDeal = offer.on_sale !== false && offer.is_best_deal && comparedShops > 1;
  const canExclude = Boolean(offer.tracking_rule_id
    && uncertain
    && offer.on_sale !== false
    && (offer.product_name || offer.suggested_exclusion_term));

  const closeMenu = useCallback((reason: DismissReason) => {
    setMenuOpen(false);
    if (reason === "escape") menuTriggerRef.current?.focus();
  }, []);
  const closeTooltip = useCallback(() => {
    setTipPinned(false);
    setTipHovered(false);
    setTipFocused(false);
  }, []);
  useDismiss(menuRef, menuOpen, closeMenu);
  useDismiss(tooltipRef, tipPinned, closeTooltip);

  async function chooseExclusion(action: ExclusionAction) {
    setWorking(true);
    setError(null);
    try {
      await onExclude(action);
      setMenuOpen(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setWorking(false);
    }
  }

  async function undoExclusion() {
    setWorking(true);
    setError(null);
    try {
      await onUndoExclude();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setWorking(false);
    }
  }

  const matchReason = offer.match_reason || "Automatická shoda nemusí odpovídat hledanému produktu.";

  return (
    <article
      data-excluded={excluded || undefined}
      className="@container/card relative flex h-full min-w-0 flex-1 flex-col rounded-2xl bg-stone-900 p-3 text-stone-100 shadow-sm shadow-black/20 ring-1 ring-stone-700 transition-shadow duration-200 hover:shadow-md"
    >
      <div className={`relative aspect-[4/3] w-full shrink-0 overflow-hidden rounded-xl bg-white ring-1 ring-stone-700 transition-opacity duration-300 ${excluded ? "grayscale opacity-50" : ""}`}>
        <ProductVisual
          imageUrl={offer.image_url}
          tag={ruleLabel}
          productName={offer.product_name}
          imageLookupMode={imageLookupMode}
        />

        {bestDeal && !excluded && (
          <span className="absolute left-2 top-2 inline-flex rounded-full bg-emerald-950 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-emerald-200 ring-1 ring-emerald-800">
            Nejlevnější
          </span>
        )}

        {uncertain && !excluded && (
          <div
            ref={tooltipRef}
            className="absolute bottom-2 left-2 z-10"
            onMouseEnter={() => setTipHovered(true)}
            onMouseLeave={() => setTipHovered(false)}
          >
            <button
              type="button"
              aria-label={`Nejistá shoda. ${matchReason}`}
              aria-describedby={showTooltip ? tooltipId : undefined}
              aria-expanded={showTooltip}
              onClick={() => setTipPinned((pinned) => !pinned)}
              onFocus={(event) => {
                try {
                  setTipFocused(event.currentTarget.matches(":focus-visible"));
                } catch {
                  setTipFocused(true);
                }
              }}
              onBlur={() => setTipFocused(false)}
              onKeyDown={(event) => {
                if (event.key === "Escape") closeTooltip();
              }}
              className="inline-flex items-center rounded-full bg-yellow-900 px-2.5 py-1 text-[11px] font-bold text-yellow-300 shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-yellow-600"
            >
              ⚠️ Nejistá shoda
            </button>
            {showTooltip && (
              <span
                id={tooltipId}
                role="tooltip"
                className="absolute bottom-full left-0 z-30 mb-2 w-[min(17rem,calc(100cqi_-_1.5rem))] rounded-lg bg-slate-950 px-3 py-2 text-xs font-medium leading-snug text-white shadow-lg"
              >
                {matchReason}
              </span>
            )}
          </div>
        )}

        {excluded && (
          <button
            type="button"
            onClick={() => void undoExclusion()}
            disabled={working}
            className="absolute bottom-2 right-2 inline-flex min-h-10 items-center gap-1.5 rounded-lg bg-stone-900 px-3 py-2 text-xs font-bold text-indigo-200 shadow-md ring-1 ring-indigo-700 transition hover:bg-stone-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:cursor-wait disabled:opacity-60"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
            Zpět (Undo)
          </button>
        )}
      </div>

      {canExclude && !excluded && (
        <div ref={menuRef} className="absolute right-3 top-3 z-20">
          <button
            type="button"
              ref={menuTriggerRef}
            onClick={() => {
              setError(null);
              setMenuOpen((open) => !open);
            }}
            aria-label={`Skrýt nebo vyloučit produkt ${label}`}
            aria-expanded={menuOpen}
              aria-controls={menuOpen ? menuId : undefined}
            aria-haspopup="dialog"
            title="Tento výsledek nechci"
            className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-stone-300 bg-white/95 text-stone-700 shadow-sm transition hover:border-red-300 hover:bg-red-50 hover:text-red-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-600"
          >
            <EyeOff className="h-5 w-5" aria-hidden="true" />
          </button>
          {menuOpen && (
            <div
              id={menuId}
              role="dialog"
              aria-label="Možnosti vyloučení produktu"
              className="absolute right-0 top-12 z-30 w-[min(19rem,calc(100cqi_-_1.5rem))] rounded-xl border border-stone-700 bg-stone-900 p-2 text-stone-100 shadow-xl"
            >
              <p className="px-2 py-1 text-xs font-semibold text-stone-300">Co mám příště skrýt?</p>
              {offer.product_name && (
                <button
                  type="button"
                  disabled={working}
                  onClick={() => void chooseExclusion({ type: "product", value: offer.product_name! })}
                  className="block w-full rounded-lg px-2 py-2 text-left text-sm font-medium text-stone-100 hover:bg-stone-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:cursor-wait disabled:opacity-50"
                >
                  Skrýt pouze tento konkrétní produkt
                </button>
              )}
              {offer.suggested_exclusion_term && (
                <button
                  type="button"
                  disabled={working}
                  onClick={() => void chooseExclusion({ type: "term", value: offer.suggested_exclusion_term! })}
                  className="block w-full rounded-lg px-2 py-2 text-left text-sm font-medium text-stone-100 hover:bg-stone-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:cursor-wait disabled:opacity-50"
                >
                  Skrýt vše se slovem „{offer.suggested_exclusion_term}“
                </button>
              )}
              {offer.temporary && <p className="px-2 pt-1 text-xs text-stone-300">Platí pouze pro toto dočasné hledání.</p>}
              {error && <p role="alert" className="px-2 pt-1 text-xs font-medium text-red-300">Uložení se nezdařilo: {error}</p>}
              <button
                type="button"
                disabled={working}
                onClick={() => setMenuOpen(false)}
                className="mt-1 w-full rounded-lg px-2 py-1.5 text-left text-xs font-medium text-stone-300 hover:bg-stone-800 hover:text-white"
              >
                Zavřít
              </button>
            </div>
          )}
        </div>
      )}

      <div className={`flex min-h-0 flex-1 flex-col pt-3 transition-opacity duration-300 @sm/card:pt-4 ${excluded ? "opacity-50" : ""}`}>
        <h3
          title={label}
          className={`min-h-[2lh] line-clamp-2 text-[0.9375rem] font-semibold leading-tight text-stone-100 @sm/card:text-base ${excluded ? "line-through" : ""}`}
        >
          {label}
        </h3>

        <div className="mt-3 min-h-[2.5lh]">
          {offer.on_sale === false ? (
            <p className="text-sm font-semibold text-stone-300">Není v akci</p>
          ) : (
            <>
              <p className={`flex flex-wrap items-baseline gap-x-[0.3em] text-[length:clamp(1.5rem,9.5cqi,2.25rem)] font-extrabold leading-none tracking-tight text-white tabular-nums ${excluded ? "line-through" : ""}`}>
                {price ? (
                  <>
                    {price.amount} <span className="text-[0.58em] font-bold">{price.currency}</span>
                  </>
                ) : offer.price ?? "Cena neuvedena"}
              </p>
              <p
                aria-hidden={!unitLabel}
                className={`mt-1 min-h-[1lh] line-clamp-1 text-sm font-medium leading-snug text-stone-300 tabular-nums ${excluded ? "line-through" : ""}`}
              >
                {unitLabel ?? " "}
              </p>
            </>
          )}
        </div>

        <footer className="mt-auto border-t border-stone-700 pt-3 text-xs text-stone-300">
          <div className={`flex min-w-0 items-end justify-between gap-2 ${excluded ? "line-through" : ""}`}>
            <div className="min-w-0">
              <p className="flex min-w-0 items-center gap-1.5 truncate font-semibold text-stone-200">
                <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: storeColor(offer.store_id) }} />
                <span className="truncate">{storeLabel(offer)}</span>
              </p>
              <p className="mt-0.5 line-clamp-1">{offer.validity || "Platnost neuvedena"}</p>
            </div>
          </div>
          {excluded && error && <p role="alert" className="mt-2 text-xs font-medium text-red-300">Vrácení se nezdařilo: {error}</p>}
        </footer>
      </div>
    </article>
  );
}
