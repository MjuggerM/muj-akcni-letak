import { useState } from "react";
import { X } from "lucide-react";
import type { TrackingRule } from "../types";
import { savePreferences } from "../api/client";
import { TrackedItemsManager } from "./TrackedItemsManager";

interface Props {
  onClose: () => void;
  trackedItems: TrackingRule[];
  maxItems: number;
  onAddBroad?: (name: string, excluded: string[]) => boolean;
  onAddExact?: (query: string, productName: string) => boolean;
  onRemove: (id: string) => void;
  onUpdateExcludedTerms: (id: string, excludedTerms: string[]) => void;
  selectedStores: string[];
  onToggleStore: (id: string) => void;
}

export function SettingsModal({
  onClose,
  trackedItems,
  maxItems,
  onAddBroad,
  onAddExact,
  onRemove,
  onUpdateExcludedTerms,
  selectedStores,
  onToggleStore,
}: Props) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await savePreferences({ tracking_rules: trackedItems, default_stores: selectedStores });
      onClose();
    } catch (err: any) {
      setError(err?.message ?? String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-2xl rounded-lg bg-white p-6">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">⚙️ Nastavení</h3>
          <button onClick={onClose} className="text-stone-500 hover:text-stone-700"><X className="h-5 w-5" /></button>
        </div>

        <div className="mt-4">
          <TrackedItemsManager
            trackedItems={trackedItems}
            maxItems={maxItems}
            onAddBroad={onAddBroad ?? (() => false)}
            onAddExact={onAddExact ?? (() => false)}
            onRemove={onRemove}
            onUpdateExcludedTerms={onUpdateExcludedTerms}
          />
        </div>

        <div className="mt-4">
          <h4 className="text-sm font-medium">Vybrané obchody</h4>
          <div className="mt-2 flex flex-wrap gap-2">
            {Object.entries({ lidl: "Lidl", penny: "Penny", billa: "Billa", albert: "Albert" }).map(([id, label]) => (
              <label key={id} className="inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm">
                <input type="checkbox" checked={selectedStores.includes(id)} onChange={() => onToggleStore(id)} />
                <span>{label}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="mt-6 flex items-center justify-end gap-3">
          {error && <div className="text-sm text-rose-600">{error}</div>}
          <button onClick={onClose} className="rounded-md border px-3 py-1.5 text-sm">Zavřít</button>
          <button onClick={save} disabled={saving} className="rounded-md bg-indigo-700 px-3 py-1.5 text-sm text-white">Uložit</button>
        </div>
      </div>
    </div>
  );
}
