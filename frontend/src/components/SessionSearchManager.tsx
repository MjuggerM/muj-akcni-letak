import { Plus, X } from "lucide-react";
import { useState, type KeyboardEvent } from "react";
import type { TrackingRule } from "../types";

interface Props {
  sessionItems: TrackingRule[];
  maxItems: number;
  onAdd: (query: string) => void;
  onRemove: (id: string) => void;
}

export function SessionSearchManager({ sessionItems, maxItems, onAdd, onRemove }: Props) {
  const [input, setInput] = useState("");
  const atLimit = sessionItems.length >= maxItems;

  function submit() {
    if (!input.trim()) return;
    onAdd(input.trim());
    setInput("");
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") submit();
  }

  return (
    <div className="rounded-2xl border border-stone-800 bg-stone-900/80 p-4 shadow-lg shadow-black/20">
      <h2 className="mb-3 text-xs font-bold uppercase tracking-wide text-stone-300">Dočasné hledání</h2>
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={atLimit}
          placeholder="např. vejce (dočasně)"
          className="flex-1 rounded-lg border border-stone-700 bg-stone-950 px-3 py-2 text-sm text-stone-100 placeholder:text-stone-500"
        />
        <button
          type="button"
          onClick={submit}
          disabled={atLimit || !input.trim()}
          className="flex items-center justify-center rounded-lg bg-indigo-600 px-3 text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {sessionItems.length === 0 && <p className="text-sm text-stone-400">Žádné dočasné položky.</p>}
        {sessionItems.map((item) => (
          <span key={item.id} className="inline-flex items-center gap-1.5 rounded-full bg-indigo-500/15 py-1 pl-3 pr-2 text-sm text-indigo-200 ring-1 ring-indigo-500/30">
            {item.label}
            <button type="button" onClick={() => onRemove(item.id)} className="rounded-full p-0.5 text-indigo-300 hover:bg-indigo-500/20 hover:text-white">
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
      </div>
    </div>
  );
}
