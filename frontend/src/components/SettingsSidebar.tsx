import { useEffect, useState } from "react";
import { Check, Settings } from "lucide-react";

import { savePreferences, type ImageLookupMode } from "../api/client";
import type { Store, TrackingRule } from "../types";
import { StoreFilter } from "./StoreFilter";
import { TrackedItemsManager } from "./TrackedItemsManager";

interface Props {
  trackedItems: TrackingRule[];
  maxItems: number;
  onAddBroad: (name: string, excludedTerms: string[], excludedProducts: string[]) => boolean;
  onAddExact: (query: string, productName: string) => boolean;
  onRemove: (id: string) => void;
  onUpdateExcludedTerms: (id: string, excludedTerms: string[]) => void;
  onUpdateExcludedProducts: (id: string, excludedProducts: string[]) => void;
  stores: Store[];
  selectedStores: string[];
  onToggleStore: (id: string) => void;
  showNotOnSale: boolean;
  onShowNotOnSaleChange: (show: boolean) => void;
  imageLookupMode: ImageLookupMode;
  onImageLookupModeChange: (mode: ImageLookupMode) => void;
}

export function SettingsSidebar({
  trackedItems,
  maxItems,
  onAddBroad,
  onAddExact,
  onRemove,
  onUpdateExcludedTerms,
  onUpdateExcludedProducts,
  stores,
  selectedStores,
  onToggleStore,
  showNotOnSale,
  onShowNotOnSaleChange,
  imageLookupMode,
  onImageLookupModeChange,
}: Props) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSaved(false);
  }, [trackedItems, selectedStores]);

  async function save() {
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      await savePreferences({ tracking_rules: trackedItems, default_stores: selectedStores });
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <aside className="space-y-4 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:self-start lg:overflow-y-auto">
      <div className="flex items-center gap-2 px-1">
        <Settings className="h-4 w-4 text-indigo-300" aria-hidden="true" />
        <h2 className="text-sm font-bold uppercase tracking-wide text-stone-200">Nastavení</h2>
      </div>

      <TrackedItemsManager
        trackedItems={trackedItems}
        maxItems={maxItems}
        onAddBroad={onAddBroad}
        onAddExact={onAddExact}
        onRemove={onRemove}
        onUpdateExcludedTerms={onUpdateExcludedTerms}
        onUpdateExcludedProducts={onUpdateExcludedProducts}
      />

      <StoreFilter stores={stores} selectedStores={selectedStores} onToggle={onToggleStore} />

      <section className="rounded-2xl border border-stone-800 bg-stone-900/80 p-4 shadow-lg shadow-black/20">
        <h3 className="mb-3 text-xs font-bold uppercase tracking-wide text-stone-300">Zobrazení</h3>
        <label className="flex items-start gap-2 text-sm text-stone-300">
          <input
            className="mt-1 accent-indigo-500"
            type="checkbox"
            checked={showNotOnSale}
            onChange={(event) => onShowNotOnSaleChange(event.target.checked)}
          />
          <span>Zobrazit i sledované položky mimo akci</span>
        </label>
      </section>

      <section className="rounded-2xl border border-stone-800 bg-stone-900/80 p-4 shadow-lg shadow-black/20">
        <h3 className="text-xs font-bold uppercase tracking-wide text-stone-300">Fotky produktů</h3>
        <label className="mt-3 flex items-start gap-2 text-sm text-stone-300">
          <input
            className="mt-1 accent-indigo-500"
            type="checkbox"
            checked={imageLookupMode === "quality"}
            onChange={(event) => onImageLookupModeChange(event.target.checked ? "quality" : "legacy")}
          />
          <span>Přesnější párování fotek</span>
        </label>
        <p className="mt-2 text-xs leading-relaxed text-stone-400">
          Přesnější režim při nejisté shodě raději fotku nezobrazí. Volba se ukládá v tomto prohlížeči.
        </p>
      </section>

      <div className="space-y-2 px-1 pb-1">
        {error && <p role="alert" className="text-sm text-rose-300">Uložení se nezdařilo: {error}</p>}
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-400/60 disabled:cursor-wait disabled:opacity-50"
        >
          {saved && <Check className="h-4 w-4" aria-hidden="true" />}
          {saving ? "Ukládám…" : saved ? "Uloženo" : "Uložit nastavení"}
        </button>
      </div>
    </aside>
  );
}
