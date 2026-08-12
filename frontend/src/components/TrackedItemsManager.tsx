import { ChevronDown, ChevronUp, Plus, Search, SlidersHorizontal, X } from "lucide-react";
import { useState, type KeyboardEvent } from "react";

import { fetchProductSuggestions } from "../api/client";
import type { TrackingRule } from "../types";

interface TrackedItemsManagerProps {
  trackedItems: TrackingRule[];
  maxItems: number;
  onAddBroad: (name: string, excludedTerms: string[]) => boolean;
  onAddExact: (query: string, productName: string) => boolean;
  onRemove: (id: string) => void;
  onUpdateExcludedTerms: (id: string, excludedTerms: string[]) => void;
}

function splitTerms(value: string) {
  return value.split(",").map((term) => term.trim()).filter(Boolean);
}

export function TrackedItemsManager({
  trackedItems,
  maxItems,
  onAddBroad,
  onAddExact,
  onRemove,
  onUpdateExcludedTerms,
}: TrackedItemsManagerProps) {
  const [query, setQuery] = useState("");
  const [excludedTerms, setExcludedTerms] = useState("");
  const [precisionOpen, setPrecisionOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [suggestionLoading, setSuggestionLoading] = useState(false);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingExcludedTerms, setEditingExcludedTerms] = useState("");
  const atLimit = trackedItems.length >= maxItems;

  function addBroad() {
    if (!query.trim()) return;
    if (onAddBroad(query, splitTerms(excludedTerms))) {
      setQuery("");
      setExcludedTerms("");
      setSuggestions([]);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") addBroad();
  }

  async function findSuggestions() {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setSuggestionError("Zadej alespoň dva znaky.");
      return;
    }
    setSuggestionLoading(true);
    setSuggestionError(null);
    try {
      setSuggestions(await fetchProductSuggestions(trimmed));
    } catch {
      setSuggestions([]);
      setSuggestionError("Přesné produkty se teď nepodařilo načíst.");
    } finally {
      setSuggestionLoading(false);
    }
  }

  function chooseExact(productName: string) {
    if (onAddExact(query, productName)) {
      setQuery("");
      setExcludedTerms("");
      setSuggestions([]);
      setPrecisionOpen(false);
    }
  }

  function startEditing(item: TrackingRule) {
    setEditingId(item.id);
    setEditingExcludedTerms(item.excluded_terms.join(", "));
  }

  function cancelEditing() {
    setEditingId(null);
    setEditingExcludedTerms("");
  }

  function saveEditing() {
    if (!editingId) return;
    onUpdateExcludedTerms(editingId, splitTerms(editingExcludedTerms));
    cancelEditing();
  }

  return (
    <div className="rounded-2xl border border-stone-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-xs font-bold uppercase tracking-wide text-stone-500">Sleduji</h2>
          <p className="mt-0.5 text-xs text-stone-400">Přidej obecný výraz, nebo vyber konkrétní produkt z Kupi.</p>
        </div>
        <span className={`shrink-0 text-xs ${atLimit ? "font-semibold text-amber-700" : "text-stone-400"}`}>
          {trackedItems.length}/{maxItems}
        </span>
      </div>

      <div className="flex gap-2">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={handleKeyDown}
          disabled={atLimit}
          placeholder="např. vejce nebo Coca-Cola"
          className="min-w-0 flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm text-stone-900 placeholder:text-stone-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:bg-stone-50"
        />
        <button
          type="button"
          onClick={addBroad}
          disabled={atLimit || !query.trim()}
          className="inline-flex items-center gap-1 rounded-lg bg-indigo-700 px-3 text-sm font-medium text-white transition hover:bg-indigo-800 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Plus className="h-4 w-4" /> Přidat
        </button>
      </div>

      <button
        type="button"
        onClick={() => setPrecisionOpen((open) => !open)}
        className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-stone-500 hover:text-indigo-700"
      >
        <SlidersHorizontal className="h-3.5 w-3.5" /> Upřesnit výběr
        {precisionOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
      </button>

      {precisionOpen && (
        <div className="mt-3 rounded-xl bg-stone-50 p-3">
          <label className="block text-xs font-medium text-stone-600">
            Nezobrazovat slova
            <input
              value={excludedTerms}
              onChange={(event) => setExcludedTerms(event.target.value)}
              disabled={atLimit}
              placeholder="např. aspik, salát"
              className="mt-1 block w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
            />
          </label>
          <div className="mt-3 flex items-center gap-3">
            <button
              type="button"
              onClick={findSuggestions}
              disabled={atLimit || suggestionLoading}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-700 hover:text-indigo-900 disabled:opacity-40"
            >
              <Search className="h-3.5 w-3.5" /> {suggestionLoading ? "Hledám…" : "Vybrat přesný produkt z Kupi"}
            </button>
            {suggestionError && <span className="text-xs text-rose-600">{suggestionError}</span>}
          </div>
          {suggestions.length > 0 && (
            <div className="mt-3 border-t border-stone-200 pt-2">
              <p className="mb-1 text-xs text-stone-500">Vyber jednu konkrétní položku:</p>
              <div className="max-h-36 space-y-1 overflow-y-auto">
                {suggestions.map((productName) => (
                  <button
                    type="button"
                    key={productName}
                    onClick={() => chooseExact(productName)}
                    className="block w-full rounded-lg px-2 py-1.5 text-left text-sm text-stone-700 hover:bg-white hover:text-indigo-700"
                  >
                    {productName}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="mt-4 space-y-2">
        {trackedItems.length === 0 && <p className="text-sm text-stone-400">Zatím nesleduješ žádné položky.</p>}
        {trackedItems.map((item) => (
          <div key={item.id} className="rounded-xl border border-indigo-100 bg-indigo-50/60 p-3 text-sm text-indigo-800">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="truncate font-medium">{item.label}</span>
                  {item.match_mode === "exact" && <span className="rounded-full bg-white px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-indigo-500">přesně</span>}
                </div>
                {editingId === item.id ? (
                  <div className="mt-2 space-y-2">
                    <input
                      value={editingExcludedTerms}
                      onChange={(event) => setEditingExcludedTerms(event.target.value)}
                      placeholder="např. aspik, salát"
                      className="block w-full rounded-lg border border-indigo-200 bg-white px-3 py-2 text-sm text-stone-900 placeholder:text-stone-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                    />
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={saveEditing}
                        className="rounded-lg bg-indigo-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-800"
                      >
                        Uložit
                      </button>
                      <button
                        type="button"
                        onClick={cancelEditing}
                        className="rounded-lg border border-stone-300 bg-white px-3 py-1.5 text-xs font-medium text-stone-700 hover:bg-stone-50"
                      >
                        Zrušit
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="mt-1 text-xs text-indigo-600">
                    {item.excluded_terms.length > 0 ? `Nezobrazovat: ${item.excluded_terms.join(", ")}` : "Bez vyloučených slov"}
                  </div>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {editingId !== item.id && (
                  <button
                    type="button"
                    onClick={() => startEditing(item)}
                    className="rounded-full px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-white"
                  >
                    Upravit
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => onRemove(item.id)}
                  aria-label={`Odebrat ${item.label}`}
                  className="rounded-full p-1 text-indigo-400 hover:bg-white hover:text-indigo-700"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
