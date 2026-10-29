import { useEffect, useMemo, useState } from "react";
import { RefreshCw, ShoppingBasket } from "lucide-react";

import { fetchStores } from "./api/client";
import { SessionSearchManager } from "./components/SessionSearchManager";
import { SettingsSidebar } from "./components/SettingsSidebar";
import { OfferGrid } from "./components/OfferGrid";
import { useImageLookupMode } from "./hooks/useImageLookupMode";
import { useOffers } from "./hooks/useOffers";
import { useStoreFilter } from "./hooks/useStoreFilter";
import { useTrackedItems } from "./hooks/useTrackedItems";
import type { Store, TrackingRule } from "./types";

// Keep the paused request's empty rules array stable across renders.
const NO_RULES: TrackingRule[] = [];

export default function App() {
  const [stores, setStores] = useState<Store[]>([]);
  const {
    trackedItems,
    preferencesLoading,
    preferencesError,
    addBroadItem,
    addExactItem,
    addExclusion,
    removeItem,
    updateExcludedTerms,
    updateExcludedProducts,
    removeExclusion,
    maxTrackedItems,
  } = useTrackedItems();
  const {
    selectedStores,
    toggleStore,
    preferencesLoading: storesLoading,
    preferencesError: storesError,
  } = useStoreFilter();
  const [sessionItems, setSessionItems] = useState<typeof trackedItems>([]);
  const [showNotOnSale, setShowNotOnSale] = useState(false);
  const [imageLookupMode, setImageLookupMode] = useImageLookupMode();

  const combinedRules = useMemo(() => [...trackedItems, ...sessionItems], [trackedItems, sessionItems]);
  const ruleOrder = useMemo(() => combinedRules.map((rule) => rule.id), [combinedRules]);
  const { offers, loading, error: offersError, scrapeError, fetchedAt, refetch } = useOffers(
    preferencesLoading || storesLoading ? NO_RULES : combinedRules,
    selectedStores,
    showNotOnSale,
  );

  useEffect(() => {
    fetchStores()
      .then(setStores)
      .catch(() => setStores([]));
  }, []);

  const hasNotification = trackedItems.length > 0 && offers.length > 0;
  const visibleError = preferencesError ?? storesError ?? offersError;

  async function excludeFromOffer(ruleId: string, type: "term" | "product", value: string) {
    if (trackedItems.some((item) => item.id === ruleId)) {
      await addExclusion(ruleId, type, value);
      return;
    }

    setSessionItems((items) => items.map((item) => {
      if (item.id !== ruleId) return item;
      const key = type === "term" ? "excluded_terms" : "excluded_products";
      const values = item[key];
      return values.some((entry) => entry.toLocaleLowerCase("cs-CZ") === value.toLocaleLowerCase("cs-CZ"))
        ? item
        : { ...item, [key]: [...values, value] };
    }));
  }

  async function undoExclusionFromOffer(ruleId: string, type: "term" | "product", value: string) {
    if (trackedItems.some((item) => item.id === ruleId)) {
      await removeExclusion(ruleId, type, value);
      return;
    }

    const normalize = (entry: string) => entry.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("cs-CZ").trim();
    setSessionItems((items) => items.map((item) => {
      if (item.id !== ruleId) return item;
      const key = type === "term" ? "excluded_terms" : "excluded_products";
      return { ...item, [key]: item[key].filter((entry) => normalize(entry) !== normalize(value)) };
    }));
  }

  return (
    <div className="min-h-screen overflow-y-scroll bg-stone-950 font-sans text-stone-100">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <header className="mb-6 flex items-center justify-between gap-3 rounded-2xl border border-stone-800 bg-stone-900/80 px-4 py-3 shadow-lg shadow-black/20">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-lg shadow-indigo-900/40">
              <ShoppingBasket className="h-6 w-6" />
            </div>
            <div>
              <h1 className="font-display text-xl font-black leading-none tracking-tight text-white sm:text-2xl">
                Můj akční leták
              </h1>
              <p className="mt-1 text-sm text-stone-400">Sleduješ jen svoje položky ve svých obchodech.</p>
            </div>
          </div>
          <button
            type="button"
            onClick={refetch}
            disabled={loading || trackedItems.length === 0}
            aria-label="Obnovit nabídky"
            title="Obnovit"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-stone-700 bg-stone-800 text-stone-300 transition hover:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/40 disabled:opacity-40"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </header>

        <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <main className="min-w-0">
            {hasNotification && (
              <p className="mb-5 text-sm text-stone-300">
                <span className="font-semibold text-white">{offers.length}</span> aktuálních nabídek
                {fetchedAt && ` · aktualizováno ${new Date(fetchedAt).toLocaleTimeString("cs-CZ")}`}
              </p>
            )}

            {visibleError && (
              <p role="alert" className="mb-5 rounded-xl border border-rose-800 bg-rose-950/50 px-4 py-3 text-sm text-rose-200">
                Nepodařilo se spojit nebo načíst data z backendu: {visibleError}
              </p>
            )}

            {scrapeError && (
              <p role="alert" className="mb-5 rounded-xl border border-amber-800 bg-amber-950/50 px-4 py-3 text-sm text-amber-200">
                Kupi.cz nevrátil všechny nabídky: {scrapeError}
              </p>
            )}

            <div className="mb-6 rounded-2xl border border-stone-800 bg-stone-900/80 p-3 shadow-lg shadow-black/20">
              <SessionSearchManager
                sessionItems={sessionItems}
                maxItems={5}
                onAdd={(query) =>
                  setSessionItems((items) => [
                    ...items,
                    {
                      id: `tmp-${Date.now()}-${Math.random().toString(36).slice(2)}`,
                      query,
                      label: query,
                      match_mode: "smart",
                      exact_product_name: null,
                      excluded_terms: [],
                      excluded_products: [],
                    },
                  ])
                }
                onRemove={(id) => setSessionItems((items) => items.filter((item) => item.id !== id))}
              />
            </div>

            <OfferGrid
              offers={offers}
              ruleOrder={ruleOrder}
              loading={loading || preferencesLoading || storesLoading}
              trackedRuleCount={combinedRules.length}
              error={visibleError ?? scrapeError}
              imageLookupMode={imageLookupMode}
              onExclude={excludeFromOffer}
              onUndoExclude={undoExclusionFromOffer}
            />
          </main>

          <SettingsSidebar
            trackedItems={trackedItems}
            maxItems={maxTrackedItems}
            onAddBroad={addBroadItem}
            onAddExact={addExactItem}
            onRemove={removeItem}
            onUpdateExcludedTerms={updateExcludedTerms}
            onUpdateExcludedProducts={updateExcludedProducts}
            stores={stores}
            selectedStores={selectedStores}
            onToggleStore={toggleStore}
            showNotOnSale={showNotOnSale}
            onShowNotOnSaleChange={setShowNotOnSale}
            imageLookupMode={imageLookupMode}
            onImageLookupModeChange={setImageLookupMode}
          />
        </div>
      </div>
    </div>
  );
}
