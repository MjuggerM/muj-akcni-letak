import { useEffect, useState } from "react";

import type { ImageLookupMode } from "../api/client";
import type { Offer } from "../types";
import { getOfferKey, ProductCard } from "./ProductCard";
import type { ExclusionAction } from "./ProductCard";

interface OfferGridProps {
  offers: Offer[];
  loading: boolean;
  trackedRuleCount: number;
  error: string | null;
  imageLookupMode: ImageLookupMode;
  onExclude: (ruleId: string, type: ExclusionAction["type"], value: string) => Promise<void>;
  onUndoExclude: (ruleId: string, type: ExclusionAction["type"], value: string) => Promise<void>;
}

interface SoftExcludedOffer {
  offer: Offer;
  action: ExclusionAction | null;
}

interface OfferEntry {
  key: string;
  offer: Offer;
  ruleId: string;
  ruleLabel: string;
  comparedShops: number;
}

interface OfferGroup {
  key: string;
  ruleLabel: string;
  unit: string | null;
  entries: OfferEntry[];
}

const GRID_CLASS = "grid grid-cols-[repeat(auto-fill,minmax(min(100%,14rem),1fr))] items-stretch gap-4";

function trackedLabel(offer: Offer) {
  return typeof offer.tracked_item === "string"
    ? offer.tracked_item
    : offer.tracked_item.label ?? offer.tracked_item.keyword;
}

function ruleId(offer: Offer) {
  return offer.tracking_rule_id ?? trackedLabel(offer);
}

function normalize(value: string | null | undefined) {
  return (value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("cs-CZ")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function tokens(value: string) {
  return normalize(value).split(/\s+/).filter(Boolean);
}

function includesWordSequence(name: string, term: string) {
  const nameTokens = tokens(name);
  const termTokens = tokens(term);
  if (termTokens.length === 0 || termTokens.length > nameTokens.length) return false;
  return nameTokens.some((_, index) => termTokens.every((token, offset) => nameTokens[index + offset] === token));
}

function actionAffectsOffer(offer: Offer, action: ExclusionAction) {
  if (action.type === "product") return normalize(offer.product_name) === normalize(action.value);
  return includesWordSequence(offer.product_name ?? "", action.value)
    || normalize(offer.suggested_exclusion_term) === normalize(action.value);
}

function buildGroups(offers: Offer[]): OfferGroup[] {
  const groups = new Map<string, OfferGroup>();
  const shopSets = new Map<string, Set<string>>();

  for (const offer of offers) {
    const label = trackedLabel(offer);
    const id = ruleId(offer);
    const key = JSON.stringify([id, offer.unit]);
    if (!groups.has(key)) groups.set(key, { key, ruleLabel: label, unit: offer.unit, entries: [] });

    if (offer.on_sale !== false && offer.unit && offer.unit_price !== null) {
      const shops = shopSets.get(key) ?? new Set<string>();
      shops.add(offer.store_id ?? offer.shop_raw);
      shopSets.set(key, shops);
    }
  }

  const seenKeys = new Set<string>();
  for (const offer of offers) {
    const label = trackedLabel(offer);
    const id = ruleId(offer);
    const groupKey = JSON.stringify([id, offer.unit]);
    const baseKey = getOfferKey(offer);
    if (seenKeys.has(baseKey)) continue;
    seenKeys.add(baseKey);
    groups.get(groupKey)?.entries.push({
      key: baseKey,
      offer,
      ruleId: id,
      ruleLabel: label,
      comparedShops: shopSets.get(groupKey)?.size ?? 0,
    });
  }

  for (const group of groups.values()) {
    group.entries.sort((a, b) => {
      const aPrice = a.offer.unit_price ?? Number.POSITIVE_INFINITY;
      const bPrice = b.offer.unit_price ?? Number.POSITIVE_INFINITY;
      if (aPrice !== bPrice) return aPrice < bPrice ? -1 : 1;
      return (a.offer.product_name ?? "").localeCompare(b.offer.product_name ?? "", "cs-CZ");
    });
  }
  return [...groups.values()];
}

function unitHeading(unit: string | null) {
  if (!unit) return "Nabídky bez porovnatelné měrné ceny";
  return `Cena za ${unit}`;
}

function LoadingCards() {
  return (
    <ul aria-label="Načítání nabídek" className={GRID_CLASS}>
      {Array.from({ length: 6 }, (_, index) => (
        <li key={index} className="min-w-0 animate-pulse rounded-2xl bg-stone-900 p-3 shadow-sm ring-1 ring-stone-700">
          <div className="aspect-[4/3] rounded-xl bg-white" />
          <div className="mt-4 h-4 w-3/4 rounded bg-stone-800" />
          <div className="mt-2 h-4 w-1/2 rounded bg-stone-800" />
          <div className="mt-6 h-8 w-2/3 rounded bg-stone-800" />
          <div className="mt-4 h-8 rounded bg-stone-800" />
        </li>
      ))}
    </ul>
  );
}

export function OfferGrid({ offers, loading, trackedRuleCount, error, imageLookupMode, onExclude, onUndoExclude }: OfferGridProps) {
  const [softExcludedOffers, setSoftExcludedOffers] = useState<Record<string, SoftExcludedOffer>>({});

  useEffect(() => {
    const liveOfferKeys = new Set(offers.map(getOfferKey));
    setSoftExcludedOffers((current) => {
      let changed = false;
      const next = { ...current };
      for (const [key, cached] of Object.entries(current)) {
        if (cached.action === null && liveOfferKeys.has(key)) {
          delete next[key];
          changed = true;
        }
      }
      return changed ? next : current;
    });
  }, [offers]);

  // Keep the affected cards in their grid cells while an exclusion refetch is in flight.
  const offersByKey = new Map(offers.map((offer) => [getOfferKey(offer), offer]));
  for (const [key, cached] of Object.entries(softExcludedOffers)) {
    if (!offersByKey.has(key)) offersByKey.set(key, cached.offer);
  }
  const groups = buildGroups([...offersByKey.values()]);
  const entries = groups.flatMap((group) => group.entries);

  async function exclude(entry: OfferEntry, action: ExclusionAction) {
    const id = entry.offer.tracking_rule_id;
    if (!id) return;
    await onExclude(id, action.type, action.value);

    const affected = entries.filter((candidate) => candidate.ruleId === entry.ruleId
      && (candidate.key === entry.key || actionAffectsOffer(candidate.offer, action)));
    setSoftExcludedOffers((current) => {
      const next = { ...current };
      for (const candidate of affected) next[candidate.key] = { offer: candidate.offer, action };
      return next;
    });
  }

  async function undo(entryKey: string) {
    const cached = softExcludedOffers[entryKey];
    const id = cached?.offer.tracking_rule_id;
    if (!cached?.action || !id) return;
    const { action, offer } = cached;
    await onUndoExclude(id, action.type, action.value);

    setSoftExcludedOffers((current) => {
      const next = { ...current };
      for (const [key, candidate] of Object.entries(current)) {
        if (candidate.action
          && ruleId(candidate.offer) === ruleId(offer)
          && candidate.action.type === action.type
          && normalize(candidate.action.value) === normalize(action.value)) {
          next[key] = { ...candidate, action: null };
        }
      }
      return next;
    });
  }

  if (groups.length === 0 && loading && trackedRuleCount > 0) return <LoadingCards />;
  if (groups.length === 0) {
    const emptyMessage = trackedRuleCount === 0
      ? "Zatím nic nesleduješ. Přidej položku v nastavení nebo použij dočasné hledání."
      : error
        ? "Nabídky se nepodařilo načíst. Zkontroluj připojení a zkus obnovit výsledky."
        : "Žádné akce na sledované položky ve vybraných obchodech.";
    return (
      <section aria-label="Porovnání nabídek" className="@container mb-8">
        <p role="status" className="rounded-2xl border border-dashed border-stone-700 bg-stone-900 px-6 py-12 text-center text-sm text-stone-300">
          {emptyMessage}
        </p>
      </section>
    );
  }

  return (
    <section aria-label="Porovnání nabídek" className="@container mb-8 space-y-5 text-stone-100">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-lg font-bold tracking-tight text-white">Porovnání cen</h2>
        {loading && <span className="text-xs font-medium text-stone-400">Aktualizuji nabídky…</span>}
      </div>

      {groups.map((group) => (
        <section key={group.key} aria-label={`${group.ruleLabel}, ${unitHeading(group.unit)}`} className="min-w-0">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <h3 className="min-w-0 truncate text-sm font-bold text-stone-200">{group.ruleLabel}</h3>
            <p className="shrink-0 text-xs font-medium text-stone-400">
              {unitHeading(group.unit)}
              {group.entries[0]?.comparedShops > 1 && ` · ${group.entries[0].comparedShops} obchodů`}
            </p>
          </div>
          <ul className={`${GRID_CLASS} @container`}>
            {group.entries.map((entry) => (
              <li key={entry.key} className="flex min-w-0">
                <ProductCard
                  offer={entry.offer}
                  ruleLabel={entry.ruleLabel}
                  comparedShops={entry.comparedShops}
                  imageLookupMode={imageLookupMode}
                  excluded={Boolean(softExcludedOffers[entry.key]?.action)}
                  onExclude={(action) => exclude(entry, action)}
                  onUndoExclude={() => undo(entry.key)}
                />
              </li>
            ))}
          </ul>
        </section>
      ))}
    </section>
  );
}
