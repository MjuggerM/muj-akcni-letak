import { useEffect, useState } from "react";
import { API_BASE_URL } from "../api/client";
import { VISUAL_SOURCES } from "../visuals";

interface ProductVisualProps {
  imageUrl: string | null;
  tag: string;
  visualKey?: string | null;
  productName: string | null;
  size?: "card" | "hit";
}

// In-memory within this tab's lifetime: avoids duplicate network calls for
// the same product appearing in both OfferList and TopHits at once.
const imageCache = new Map<string, Promise<string | null>>();

// Backed by sessionStorage so a page reload doesn't forget we were just
// rate-limited and immediately re-fire the same request. This is a client-side
// safety net; the real fix is the backend's own short-lived failure cache in
// image_cache.py, which is shared across all users/tabs. This just keeps a
// single tab from re-asking for what it already knows was recently refused.
const COOLDOWN_STORAGE_KEY = "muj-akcni-letak:image-cooldowns";
const COOLDOWN_MS = 15000;

function readCooldowns(): Record<string, number> {
  try {
    return JSON.parse(sessionStorage.getItem(COOLDOWN_STORAGE_KEY) ?? "{}");
  } catch {
    return {};
  }
}

function canRequestAgain(cacheKey: string) {
  const cooldowns = readCooldowns();
  const now = Date.now();
  const lastRequest = cooldowns[cacheKey] ?? 0;
  if (now - lastRequest < COOLDOWN_MS) {
    return false;
  }
  cooldowns[cacheKey] = now;
  // Trim old entries so this doesn't grow unbounded over a long session.
  for (const key of Object.keys(cooldowns)) {
    if (now - cooldowns[key] > COOLDOWN_MS * 10) delete cooldowns[key];
  }
  try {
    sessionStorage.setItem(COOLDOWN_STORAGE_KEY, JSON.stringify(cooldowns));
  } catch {
    // sessionStorage full or unavailable (e.g. private mode) - degrade to
    // "always allow", which just means we lose the cross-reload cooldown.
  }
  return true;
}

function isValidImageUrl(value: string | null | undefined) {
  return Boolean(value && /^https?:\/\//i.test(value));
}

function normalizeQuery(value: string | null | undefined) {
  return (value ?? "").trim().replace(/\s+/g, " ");
}

function lookupVisualQuery(visualKey: string | null | undefined) {
  if (!visualKey) {
    return null;
  }
  return VISUAL_SOURCES[visualKey]?.remoteQuery ?? null;
}

function resolveImageQuery(productName: string | null, tag: string, visualKey: string | null | undefined) {
  return normalizeQuery(productName) || normalizeQuery(tag) || lookupVisualQuery(visualKey) || null;
}

function Placeholder({ label, sizeClass }: { label: string; sizeClass: string }) {
  return (
    <div
      aria-hidden="true"
      className={`${sizeClass} flex shrink-0 items-center justify-center rounded-lg bg-stone-800 text-[10px] font-bold uppercase tracking-[0.18em] text-stone-400 ring-1 ring-stone-700`}
    >
      {label}
    </div>
  );
}

async function fetchProductImageByName(productName: string | null, fallbackUrl: string | null) {
  if (isValidImageUrl(fallbackUrl)) {
    return fallbackUrl;
  }

  const query = normalizeQuery(productName);
  if (!query) {
    return null;
  }

  const cacheKey = `name:${query.toLowerCase()}`;
  if (imageCache.has(cacheKey)) {
    return imageCache.get(cacheKey)!;
  }

  if (!canRequestAgain(cacheKey)) {
    return null;
  }

  const request = (async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/proxy-image?query=${encodeURIComponent(query)}`);

      if (!response.ok) {
        if (response.status === 429) {
          console.error("❌ API nás zablokovalo (Rate Limit) pro název:", query);
        }
        return null;
      }

      const data = (await response.json()) as { image_url?: string | null; imageUrl?: string | null };
      return data.imageUrl ?? data.image_url ?? null;
    } catch (error) {
      console.error("❌ Chyba při stahování přes backend proxy:", error);
      return null;
    }
  })();

  imageCache.set(cacheKey, request);

  // On a null result we deliberately do NOT delete the cache entry anymore:
  // the backend now remembers "miss"/"failure" outcomes itself (with its own
  // TTLs), so re-fetching on every re-render here would defeat that and just
  // recreate the original problem. The per-tab cooldown above already gates
  // retries; letting this promise cache stand means we won't even ask again
  // within the same tab until a fresh mount needs it.

  return request;
}

export function ProductVisual({ imageUrl, tag, visualKey, productName, size = "card" }: ProductVisualProps) {
  const [resolvedImage, setResolvedImage] = useState<string | null>(imageUrl ?? null);
  const [imageFailed, setImageFailed] = useState(false);
  const [isFetching, setIsFetching] = useState(!isValidImageUrl(imageUrl));
  const sizeClass = size === "hit" ? "h-14 w-14" : "h-16 w-16";

  useEffect(() => {
    let isActive = true;

    const nextImage = imageUrl ?? null;
    setResolvedImage(nextImage);
    setImageFailed(false);
    setIsFetching(!isValidImageUrl(nextImage));

    if (isValidImageUrl(nextImage)) {
      return () => {
        isActive = false;
      };
    }

    const sourceName = resolveImageQuery(productName, tag, visualKey);

    void (async () => {
      const image = await fetchProductImageByName(sourceName, nextImage);

      if (!isActive) {
        return;
      }

      setResolvedImage(image ?? null);
      setIsFetching(false);
    })();

    return () => {
      isActive = false;
    };
  }, [imageUrl, productName, tag, visualKey]);

  if (isFetching || !resolvedImage || imageFailed) {
    const placeholderLabel = (productName ?? tag ?? lookupVisualQuery(visualKey) ?? "foto").slice(0, 12);
    return <Placeholder label={placeholderLabel} sizeClass={sizeClass} />;
  }

  return (
    <img
      src={resolvedImage}
      alt={productName ?? tag}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setImageFailed(true)}
      className={`${sizeClass} shrink-0 rounded-lg bg-stone-100 object-cover`}
    />
  );
}