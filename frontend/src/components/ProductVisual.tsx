import { useEffect, useState } from "react";
import { API_BASE_URL } from "../api/client";
import { VISUAL_SOURCES } from "../visuals";

interface ProductVisualProps {
  imageUrl: string | null;
  tag: string;
  visualKey?: string | null;
  ean?: string | null;
  productName: string | null;
  size?: "card" | "hit";
}

const imageCache = new Map<string, Promise<string | null>>();
const requestCooldown = new Map<string, number>();

function canRequestAgain(cacheKey: string) {
  const now = Date.now();
  const lastRequest = requestCooldown.get(cacheKey) ?? 0;
  if (now - lastRequest < 15000) {
    return false;
  }
  requestCooldown.set(cacheKey, now);
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

// Ordered, de-duplicated search terms to try against the backend image
// proxy: the specific scraped product name first (best match when it
// hits), then the raw tracked keyword, then - as a last resort - the
// broad category term from visuals.ts (e.g. "chicken meat" instead of
// "Kuřecí prsní řízky Vodňanské kuře 500g"). Specific Czech branded
// product names very often have no match in Open Food Facts at all, so
// falling back to a broad category term meaningfully increases the odds
// of getting *some* representative photo instead of a plain placeholder.
// This costs at most 2 extra backend requests per product, and only for
// products that miss on the first try - and thanks to the fixed negative
// caching in image_cache.py, that's a one-time cost per product name, not
// a recurring one.
function resolveImageQueries(productName: string | null, tag: string, visualKey: string | null | undefined) {
  const candidates = [normalizeQuery(productName), normalizeQuery(tag), lookupVisualQuery(visualKey)];
  const seen = new Set<string>();
  const queries: string[] = [];
  for (const candidate of candidates) {
    if (candidate && !seen.has(candidate.toLowerCase())) {
      seen.add(candidate.toLowerCase());
      queries.push(candidate);
    }
  }
  return queries;
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

// NOTE: `ean` is currently always undefined in practice. kupiapi's raw
// scraper output (backend/app/kupi_service.py) only ever contains name /
// shops / prices / amounts / validities - no barcode field exists
// anywhere in the library (checked directly against its source, both the
// published PyPI package and the current GitHub main branch), and
// backend/app/schemas.py's Offer model has no `ean` field either. So this
// function never actually fires a request today - it's kept because it's
// harmless and free to leave in if EAN scraping is ever added upstream.
// If you don't plan to add that, you can delete this function, the `ean`
// prop, and its call site below without losing anything that currently works.
async function fetchProductImageByEan(ean: string | null | undefined, fallbackUrl: string | null) {
  if (isValidImageUrl(fallbackUrl)) {
    return fallbackUrl;
  }

  const normalizedEan = normalizeQuery(ean);
  if (!normalizedEan || normalizedEan.length < 8) {
    return null;
  }

  const cacheKey = `ean:${normalizedEan}`;
  if (imageCache.has(cacheKey)) {
    return imageCache.get(cacheKey)!;
  }

  const request = (async () => {
    try {
      // ⏱ Rozprostření dotazů až na 5 vteřin
      await new Promise((resolve) => setTimeout(resolve, Math.random() * 5000));

      const response = await fetch(`${API_BASE_URL}/api/proxy-image?code=${encodeURIComponent(normalizedEan)}`);

      if (!response.ok) {
        if (response.status === 429) {
          console.error("❌ API nás zablokovalo (Rate Limit) pro EAN:", normalizedEan);
        }
        return null;
      }

      const contentType = response.headers.get("content-type") ?? "";
      const rawText = await response.text();
      if (!rawText || !contentType.includes("application/json")) {
        return null;
      }

      // Podpora obou formátů (camelCase i snake_case) pro jistotu
      const data = JSON.parse(rawText) as { image_url?: string | null; imageUrl?: string | null };
      return data.imageUrl ?? data.image_url ?? null;
    } catch {
      return null;
    }
  })();

  imageCache.set(cacheKey, request);

  request.then((res) => {
    if (!res) imageCache.delete(cacheKey);
  }).catch(() => imageCache.delete(cacheKey));

  return request;
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
      // ⏱ Rozprostření dotazů až na 5 vteřin
      await new Promise((resolve) => setTimeout(resolve, Math.random() * 5000));

      const response = await fetch(`${API_BASE_URL}/api/proxy-image?query=${encodeURIComponent(query)}`);

      if (!response.ok) {
        if (response.status === 429) {
          console.error("❌ API nás zablokovalo (Rate Limit) pro název:", query);
        }
        return null;
      }

      // Podpora obou formátů (camelCase i snake_case) pro jistotu
      const data = (await response.json()) as { image_url?: string | null; imageUrl?: string | null };
      return data.imageUrl ?? data.image_url ?? null;
    } catch (error) {
      console.error("❌ Chyba při stahování přes backend proxy:", error);
      return null;
    }
  })();

  imageCache.set(cacheKey, request);

  request.then((res) => {
    if (!res) imageCache.delete(cacheKey);
  }).catch(() => imageCache.delete(cacheKey));

  return request;
}

export function ProductVisual({ imageUrl, tag, visualKey, ean, productName, size = "card" }: ProductVisualProps) {
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

    void (async () => {
      let image = await fetchProductImageByEan(ean, nextImage);

      if (!image) {
        for (const query of resolveImageQueries(productName, tag, visualKey)) {
          image = await fetchProductImageByName(query, nextImage);
          if (image) break;
        }
      }

      if (!isActive) {
        return;
      }

      setResolvedImage(image ?? null);
      setIsFetching(false);
    })();

    return () => {
      isActive = false;
    };
  }, [ean, imageUrl, productName, tag, visualKey]);

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