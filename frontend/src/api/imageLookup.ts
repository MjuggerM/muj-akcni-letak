// Zjišťování fotky produktu přes backend (/api/proxy-image).
//
// Backend odpovídá okamžitě: "found" | "missing" | "pending" | "error". Tohle místo se postará o to,
// co s tím: u "pending" se po `retry_after` sekundách zeptá znovu.
//
// Pravidla, na kterých záleží:
//  - jedna smyčka na produkt (sdílený Promise), ať je produkt na stránce kolikrát chce;
//  - "found" a "missing" jsou KONEČNÉ odpovědi a drží se po dobu života stránky;
//  - dočasný problém (síť, výpadek OFF) se NEUKLÁDÁ: výsledek "gave_up" se z cache smaže, takže
//    další zobrazení karty to zkusí znovu. (Dřív se `null` z jednoho neúspěšného requestu držel
//    v cache až do reloadu stránky a karta zůstala placeholderem, i když backend už fotku měl.)

import { fetchImageLookup, type ImageLookupMode, type ImageLookupResponse } from "./client";

export type ImageLookupOutcome =
  | { kind: "found"; url: string }
  | { kind: "missing" }   // backend potvrdil: odpovídající fotka neexistuje -> placeholder je konečný
  | { kind: "gave_up" };  // dočasný problém -> placeholder teď, ale příště to zkus znovu

const DEFAULT_POLL_MS = 10_000;
const MIN_POLL_MS = 3_000;
const MAX_POLL_MS = 60_000;
const MAX_WAIT_MS = 30 * 60_000;      // fronta na čerstvé cache jde tempem ~9 produktů/min
const MAX_NETWORK_FAILURES = 3;

export interface LookupDeps {
  fetchLookup?: (productName: string, mode: ImageLookupMode) => Promise<ImageLookupResponse>;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
}

function isHttpUrl(value: string | null | undefined): value is string {
  return Boolean(value && /^https?:\/\//i.test(value));
}

export function createImageLookup(deps: LookupDeps = {}) {
  const fetchLookup = deps.fetchLookup ?? fetchImageLookup;
  const sleep = deps.sleep ?? ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)));
  const now = deps.now ?? Date.now;
  const shared = new Map<string, Promise<ImageLookupOutcome>>();

  async function poll(productName: string, mode: ImageLookupMode): Promise<ImageLookupOutcome> {
    const startedAt = now();
    let networkFailures = 0;

    for (;;) {
      let waitMs = DEFAULT_POLL_MS;
      try {
        const data = await fetchLookup(productName, mode);
        networkFailures = 0;

        if (data.status === "found") {
          return isHttpUrl(data.image_url) ? { kind: "found", url: data.image_url } : { kind: "missing" };
        }
        if (data.status === "missing") return { kind: "missing" };

        if (typeof data.retry_after === "number") {
          waitMs = Math.min(MAX_POLL_MS, Math.max(MIN_POLL_MS, data.retry_after * 1000));
        } else if (data.status === "error") {
          waitMs = MAX_POLL_MS;
        }
      } catch (error) {
        networkFailures += 1;
        console.warn(`[fotky] dotaz na backend pro "${productName}" selhal (${networkFailures}/${MAX_NETWORK_FAILURES}):`, error);
        if (networkFailures >= MAX_NETWORK_FAILURES) return { kind: "gave_up" };
      }

      if (now() - startedAt + waitMs > MAX_WAIT_MS) return { kind: "gave_up" };
      await sleep(waitMs);
    }
  }

  return function lookupImage(productName: string, mode: ImageLookupMode = "legacy"): Promise<ImageLookupOutcome> {
    const key = productName.trim().replace(/\s+/g, " ").toLowerCase();
    const sharedKey = `${mode}:${key}`;
    let existing = shared.get(sharedKey);
    if (!existing) {
      existing = poll(productName, mode).then((outcome) => {
        if (outcome.kind === "gave_up") shared.delete(sharedKey);
        return outcome;
      });
      shared.set(sharedKey, existing);
    }
    return existing;
  };
}

export const lookupImage = createImageLookup();
