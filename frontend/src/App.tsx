import { RefreshCw, ShoppingBasket, Settings } from "lucide-react";
import { useEffect, useState, useMemo } from "react";

import { fetchStores } from "./api/client";
import { StoreFilter } from "./components/StoreFilter";
import { TopHits } from "./components/TopHits";
import { SessionSearchManager } from "./components/SessionSearchManager";
import { SettingsModal } from "./components/SettingsModal";
import { useOffers } from "./hooks/useOffers";
import { useStoreFilter } from "./hooks/useStoreFilter";
import { useTrackedItems } from "./hooks/useTrackedItems";
import type { Store } from "./types";

export default function App() {
  const [stores, setStores] = useState<Store[]>([]);
  const { trackedItems, addBroadItem, addExactItem, removeItem, updateExcludedTerms, maxTrackedItems } = useTrackedItems();
  const { selectedStores, toggleStore } = useStoreFilter();
  const [sessionItems, setSessionItems] = useState<typeof trackedItems>([]);
  const [showNotOnSale, setShowNotOnSale] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const combinedRules = useMemo(() => [...trackedItems, ...sessionItems], [trackedItems, sessionItems]);
  const { offers, loading, fetchedAt, refetch } = useOffers(combinedRules, selectedStores, showNotOnSale);

  useEffect(() => {
    fetchStores()
      .then(setStores)
      .catch(() => setStores([]));
  }, []);

  const hasNotification = trackedItems.length > 0 && offers.length > 0;

  return (
    <div className="min-h-screen bg-stone-950 font-sans text-stone-100 overflow-y-scroll">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <header className="mb-6 flex items-center justify-between gap-3 rounded-2xl border border-stone-800 bg-stone-900/80 px-4 py-3 shadow-lg shadow-black/20">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-lg shadow-indigo-900/40">
              <ShoppingBasket className="h-6 w-6" />
            </div>
            <div>
              <h1 className="font-display text-xl font-black leading-none tracking-tight sm:text-2xl text-white">
                MŮJ AKČNÍ LETÁK
              </h1>
              <p className="mt-1 text-sm text-stone-400">Sleduješ jen svoje položky, ve svých obchodech.</p>
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

        {hasNotification && <p className="mb-5 text-sm text-stone-300"><span className="font-semibold text-white">{offers.length}</span> aktuálních nabídek{fetchedAt && ` · aktualizováno ${new Date(fetchedAt).toLocaleTimeString("cs-CZ")}`}</p>}

        <div className="mb-6 flex items-center justify-between gap-3 rounded-2xl border border-stone-800 bg-stone-900/80 p-3 shadow-lg shadow-black/20">
          <div className="flex-1">
            <SessionSearchManager
              sessionItems={sessionItems}
              maxItems={5}
              onAdd={(q) => setSessionItems((s) => [...s, { id: `tmp-${Date.now()}-${Math.random().toString(36).slice(2)}`, query: q, label: q, match_mode: "broad", exact_product_name: null, excluded_terms: [], visual_key: null }])}
              onRemove={(id) => setSessionItems((s) => s.filter((i) => i.id !== id))}
            />
          </div>
          <div className="w-80">
            <StoreFilter stores={stores} selectedStores={selectedStores} onToggle={toggleStore} />
            <div className="mt-3 flex items-center gap-2">
              <label className="flex items-center gap-2 text-sm text-stone-300">
                <input type="checkbox" checked={showNotOnSale} onChange={(e) => setShowNotOnSale(e.target.checked)} />
                Zobrazit i sledované položky mimo akci
              </label>
            </div>
          </div>
        </div>

        <div className="mb-4 flex justify-end">
          <button type="button" onClick={() => setSettingsOpen(true)} className="inline-flex items-center gap-2 rounded-md border border-stone-700 bg-stone-900 px-3 py-1.5 text-sm text-stone-100 shadow-sm shadow-black/20">
            <Settings className="h-4 w-4" /> ⚙️ Nastavení
          </button>
        </div>

        <TopHits allOffers={offers} />

        {settingsOpen && (
          <SettingsModal
            onClose={() => setSettingsOpen(false)}
            trackedItems={trackedItems}
            maxItems={maxTrackedItems}
            onAddBroad={addBroadItem}
            onAddExact={addExactItem}
            onRemove={removeItem}
            onUpdateExcludedTerms={updateExcludedTerms}
            selectedStores={selectedStores}
            onToggleStore={toggleStore}
          />
        )}
      </div>
    </div>
  );
}
