import { Check, ChevronDown, ChevronUp, EyeOff, Plus, Search, X } from "lucide-react";
import { useState, type KeyboardEvent } from "react";

import { fetchProductPreview, fetchProductSuggestions } from "../api/client";
import type { ProductPreview, TrackingRule } from "../types";

interface TrackedItemsManagerProps {
  trackedItems: TrackingRule[];
  maxItems: number;
  onAddBroad: (query: string, excludedTerms: string[], excludedProducts: string[]) => boolean;
  onAddExact: (query: string, productName: string) => boolean;
  onRemove: (id: string) => void;
  onUpdateExcludedTerms: (id: string, excludedTerms: string[]) => void;
  onUpdateExcludedProducts: (id: string, excludedProducts: string[]) => void;
}

function splitTerms(value: string) {
  return value.split(",").map((term) => term.trim()).filter(Boolean);
}

function normalize(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("cs-CZ").trim();
}

function confidenceLabel(confidence: ProductPreview["confidence"]) {
  if (confidence === "high") return { text: "Dobrá shoda", className: "bg-emerald-500/15 text-emerald-300" };
  if (confidence === "medium") return { text: "Nejistá shoda", className: "bg-amber-500/15 text-amber-200" };
  return { text: "Slabá shoda", className: "bg-orange-500/15 text-orange-200" };
}

export function TrackedItemsManager({
  trackedItems,
  maxItems,
  onAddBroad,
  onAddExact,
  onRemove,
  onUpdateExcludedTerms,
  onUpdateExcludedProducts,
}: TrackedItemsManagerProps) {
  const [query, setQuery] = useState("");
  const [preview, setPreview] = useState<ProductPreview[]>([]);
  const [previewQuery, setPreviewQuery] = useState("");
  const [previewExcludedTerms, setPreviewExcludedTerms] = useState<string[]>([]);
  const [previewExcludedProducts, setPreviewExcludedProducts] = useState<string[]>([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [addError, setAddError] = useState<string | null>(null);
  const [precisionOpen, setPrecisionOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [suggestionLoading, setSuggestionLoading] = useState(false);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingExcludedTerms, setEditingExcludedTerms] = useState("");
  const [editingExcludedProducts, setEditingExcludedProducts] = useState("");
  const atLimit = trackedItems.length >= maxItems;

  function clearPreview() {
    setPreview([]);
    setPreviewQuery("");
    setPreviewExcludedTerms([]);
    setPreviewExcludedProducts([]);
    setPreviewError(null);
    setAddError(null);
  }

  async function findPreview() {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setPreviewError("Zadej alespoň dva znaky.");
      return;
    }
    setPreviewLoading(true);
    setPreviewError(null);
    setAddError(null);
    setPreviewExcludedTerms([]);
    setPreviewExcludedProducts([]);
    try {
      const results = await fetchProductPreview(trimmed);
      setPreview(results);
      setPreviewQuery(trimmed);
      if (results.length === 0) setPreviewError("Kupi pro tento dotaz nevrátil žádný odpovídající produkt.");
    } catch (err) {
      setPreview([]);
      setPreviewQuery(trimmed);
      setPreviewError(err instanceof Error ? err.message : String(err));
    } finally {
      setPreviewLoading(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") void findPreview();
  }

  function saveSmartRule() {
    if (!previewQuery) return;
    if (onAddBroad(previewQuery, previewExcludedTerms, previewExcludedProducts)) {
      setQuery("");
      clearPreview();
      setSuggestions([]);
      setPrecisionOpen(false);
    } else {
      setAddError("Položku už sleduješ nebo je dosažen limit.");
    }
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

  function resetAfterAdd() {
    setQuery("");
    setSuggestions([]);
    setSuggestionError(null);
    clearPreview();
    setPrecisionOpen(false);
  }

  function chooseExact(productName: string) {
    if (onAddExact(query, productName)) {
      resetAfterAdd();
    } else {
      setAddError("Položku už sleduješ nebo je dosažen limit.");
    }
  }

  function startEditing(item: TrackingRule) {
    setEditingId(item.id);
    setEditingExcludedTerms(item.excluded_terms.join(", "));
    setEditingExcludedProducts(item.excluded_products.join(", "));
  }

  function cancelEditing() {
    setEditingId(null);
    setEditingExcludedTerms("");
    setEditingExcludedProducts("");
  }

  function saveEditing() {
    if (!editingId) return;
    onUpdateExcludedTerms(editingId, splitTerms(editingExcludedTerms));
    onUpdateExcludedProducts(editingId, splitTerms(editingExcludedProducts));
    cancelEditing();
  }

  function togglePreviewProduct(productName: string) {
    setPreviewExcludedProducts((current) => current.some((name) => normalize(name) === normalize(productName))
      ? current.filter((name) => normalize(name) !== normalize(productName))
      : [...current, productName]);
  }

  function togglePreviewTerm(term: string) {
    setPreviewExcludedTerms((current) => current.some((name) => normalize(name) === normalize(term))
      ? current.filter((name) => normalize(name) !== normalize(term))
      : [...current, term]);
  }

  function exclusionState(item: ProductPreview) {
    const excludedProduct = previewExcludedProducts.some((name) => normalize(name) === normalize(item.product_name));
    const excludedTerm = Boolean(item.suggested_exclusion_term && previewExcludedTerms.some(
      (term) => normalize(term) === normalize(item.suggested_exclusion_term!),
    ));
    return { excludedProduct, excludedTerm, excluded: excludedProduct || excludedTerm };
  }

  return (
    <div className="rounded-2xl border border-stone-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-xs font-bold uppercase tracking-wide text-stone-500">Sleduji</h2>
          <p className="mt-0.5 text-xs text-stone-400">Napiš, co hledáš, a před uložením zkontroluj návrhy.</p>
        </div>
        <span className={`shrink-0 text-xs ${atLimit ? "font-semibold text-amber-700" : "text-stone-400"}`}>
          {trackedItems.length}/{maxItems}
        </span>
      </div>

      <div className="flex gap-2">
        <input
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            clearPreview();
            setSuggestions([]);
            setSuggestionError(null);
          }}
          onKeyDown={handleKeyDown}
          disabled={atLimit || previewLoading}
          placeholder="např. kuřecí maso nebo vejce"
          className="min-w-0 flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm text-stone-900 placeholder:text-stone-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100 disabled:bg-stone-50"
        />
        <button
          type="button"
          onClick={() => void findPreview()}
          disabled={atLimit || previewLoading || !query.trim()}
          className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-indigo-700 px-3 text-sm font-medium text-white transition hover:bg-indigo-800 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Search className="h-4 w-4" /> {previewLoading ? "Hledám…" : "Náhled"}
        </button>
      </div>

      <button
        type="button"
        onClick={() => setPrecisionOpen((open) => !open)}
        className="mt-3 inline-flex items-center gap-1.5 text-xs font-medium text-stone-500 hover:text-indigo-700"
      >
        <Search className="h-3.5 w-3.5" /> Vybrat přesný produkt z Kupi
        {precisionOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
      </button>

      {precisionOpen && (
        <div className="mt-3 rounded-xl bg-stone-50 p-3">
          <button
            type="button"
            onClick={() => void findSuggestions()}
            disabled={atLimit || suggestionLoading}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-700 hover:text-indigo-900 disabled:opacity-40"
          >
            <Search className="h-3.5 w-3.5" /> {suggestionLoading ? "Hledám…" : "Načíst konkrétní názvy"}
          </button>
          {suggestionError && <p role="alert" className="mt-2 text-xs text-rose-600">{suggestionError}</p>}
          {suggestions.length > 0 && (
            <div className="mt-3 max-h-40 space-y-1 overflow-y-auto border-t border-stone-200 pt-2">
              {suggestions.map((productName) => (
                <button
                  type="button"
                  key={productName}
                  onClick={() => chooseExact(productName)}
                  className="block w-full rounded-lg px-2 py-1.5 text-left text-sm text-stone-700 hover:bg-white hover:text-indigo-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
                >
                  {productName}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {previewQuery && (
        <div className="mt-4 rounded-xl border border-indigo-100 bg-indigo-50/60 p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold text-stone-800">Náhled pro „{previewQuery}“</h3>
              <p className="text-xs text-stone-500">Náhled až 10 shod z Kupi. Před uložením můžeš označit, co vynechat.</p>
            </div>
            <button type="button" onClick={clearPreview} aria-label="Zavřít náhled" className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-stone-500 hover:bg-white hover:text-stone-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500">
              <X className="h-4 w-4" />
            </button>
          </div>

          {preview.length > 0 ? (
            <div className="max-h-72 space-y-2 overflow-y-auto">
              {preview.map((item) => {
              const state = exclusionState(item);
              const confidence = confidenceLabel(item.confidence);
              return (
                <article key={item.product_name} className={`rounded-lg border border-stone-200 bg-white p-2.5 transition ${state.excluded ? "opacity-60" : ""}`}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className={`text-sm font-medium leading-tight text-stone-800 ${state.excluded ? "line-through" : ""}`}>{item.product_name}</p>
                      <span className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold ${confidence.className}`}>{confidence.text}</span>
                      {item.match_reason && <p className="mt-1 text-xs leading-relaxed text-stone-500">{item.match_reason}</p>}
                    </div>
                    {state.excluded && <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-label="Označeno k vynechání" />}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {state.excludedProduct ? (
                      <button type="button" onClick={() => togglePreviewProduct(item.product_name)} className="text-xs font-medium text-indigo-700 hover:underline">Vrátit tento produkt</button>
                    ) : (
                      <button type="button" onClick={() => togglePreviewProduct(item.product_name)} className="inline-flex items-center gap-1 text-xs font-medium text-stone-600 hover:text-rose-700">
                        <EyeOff className="h-3.5 w-3.5" /> Skrýt produkt
                      </button>
                    )}
                    {item.suggested_exclusion_term && (state.excludedTerm ? (
                      <button type="button" onClick={() => togglePreviewTerm(item.suggested_exclusion_term!)} className="text-xs font-medium text-indigo-700 hover:underline">Vrátit typ „{item.suggested_exclusion_term}“</button>
                    ) : (
                      <button type="button" onClick={() => togglePreviewTerm(item.suggested_exclusion_term!)} className="text-xs font-medium text-amber-700 hover:underline">
                        Skrýt typ „{item.suggested_exclusion_term}“
                      </button>
                    ))}
                  </div>
                </article>
              );
              })}
            </div>
          ) : (
            <p className="rounded-lg bg-white px-3 py-2 text-xs leading-relaxed text-stone-600">
              {previewError ?? "Náhled neobsahuje žádné produkty. Dotaz můžeš přesto začít sledovat."}
            </p>
          )}

          <button
            type="button"
            onClick={saveSmartRule}
            disabled={atLimit}
            className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-700 px-3 py-2 text-sm font-semibold text-white hover:bg-indigo-800 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Plus className="h-4 w-4" /> Sledovat tento dotaz
          </button>
          {addError && <p role="alert" className="mt-2 text-xs text-rose-600">{addError}</p>}
        </div>
      )}
      {previewError && !previewQuery && <p role="alert" className="mt-2 text-xs text-rose-600">{previewError}</p>}
      {!previewQuery && addError && <p role="alert" className="mt-2 text-xs text-rose-600">{addError}</p>}

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
                    <label className="block text-xs font-medium text-stone-600">
                      Vyloučené typy
                      <input value={editingExcludedTerms} onChange={(event) => setEditingExcludedTerms(event.target.value)} placeholder="např. párek, aspik" className="mt-1 block w-full rounded-lg border border-indigo-200 bg-white px-3 py-2 text-sm text-stone-900 placeholder:text-stone-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100" />
                    </label>
                    <label className="block text-xs font-medium text-stone-600">
                      Vyloučené konkrétní produkty
                      <input value={editingExcludedProducts} onChange={(event) => setEditingExcludedProducts(event.target.value)} placeholder="celé názvy oddělené čárkou" className="mt-1 block w-full rounded-lg border border-indigo-200 bg-white px-3 py-2 text-sm text-stone-900 placeholder:text-stone-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100" />
                    </label>
                    <div className="flex items-center gap-2">
                      <button type="button" onClick={saveEditing} className="rounded-lg bg-indigo-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-800">Uložit</button>
                      <button type="button" onClick={cancelEditing} className="rounded-lg border border-stone-300 bg-white px-3 py-1.5 text-xs font-medium text-stone-700 hover:bg-stone-50">Zrušit</button>
                    </div>
                  </div>
                ) : (
                  <div className="mt-1 text-xs text-indigo-600">
                    {item.excluded_terms.length > 0 && <p>Vyloučené typy: {item.excluded_terms.join(", ")}</p>}
                    {item.excluded_products.length > 0 && <p className="mt-1">Vyloučené produkty: {item.excluded_products.join(", ")}</p>}
                    {item.excluded_terms.length === 0 && item.excluded_products.length === 0 && <p>Bez výjimek</p>}
                  </div>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {editingId !== item.id && (
                  <button type="button" onClick={() => startEditing(item)} className="rounded-full px-2 py-1 text-xs font-medium text-indigo-700 hover:bg-white">Upravit výjimky</button>
                )}
                <button type="button" onClick={() => onRemove(item.id)} aria-label={`Odebrat ${item.label}`} title={`Odebrat ${item.label}`} className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white text-rose-600 shadow-sm ring-1 ring-rose-200 transition hover:bg-rose-50 hover:text-rose-700 hover:ring-rose-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 focus-visible:ring-offset-1">
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
