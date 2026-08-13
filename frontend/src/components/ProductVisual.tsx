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
    console.log(`⏱️ [FE Cooldown] Pro klíč '${cacheKey}' platí 15s cooldown (uběhlo ${now - lastRequest} ms). Vynechávám.`);
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
    console.log(`⚡ [FE Cache HIT] Našel jsem v paměti JS pro EAN: '${cacheKey}'`);
    return imageCache.get(cacheKey)!;
  }

  const request = (async () => {
    try {
      const delay = Math.random() * 5000;
      console.log(`⏳ [FE Jitter] Rozprostírám dotaz pro EAN '${normalizedEan}' o ${(delay / 1000).toFixed(2)}s`);
      await new Promise((resolve) => setTimeout(resolve, delay));

      const url = `${API_BASE_URL}/api/proxy-image?code=${encodeURIComponent(normalizedEan)}`;
      console.log(`🌐 [FE 2/4] Volám backend EAN proxy -> ${url}`);

      const response = await fetch(url);

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

      const data = JSON.parse(rawText) as { image_url?: string | null; imageUrl?: string | null };
      const result = data.imageUrl ?? data.image_url ?? null;
      console.log(`📥 [FE 3/4] Výsledek pro EAN '${normalizedEan}':`, result);
      return result;
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
    console.log(`⚡ [FE Cache HIT] Našel jsem v paměti JS pro Name: '${cacheKey}'`);
    return imageCache.get(cacheKey)!;
  }

  if (!canRequestAgain(cacheKey)) {
    return null;
  }

  const request = (async () => {
    try {
      const delay = Math.random() * 5000;
      console.log(`⏳ [FE Jitter] Rozprostírám dotaz pro '${query}' o ${(delay / 1000).toFixed(2)}s`);
      await new Promise((resolve) => setTimeout(resolve, delay));

      const url = `${API_BASE_URL}/api/proxy-image?query=${encodeURIComponent(query)}`;
      console.log(`🌐 [FE 2/4] Volám backend Name proxy -> ${url}`);

      const response = await fetch(url);

      if (!response.ok) {
        if (response.status === 429) {
          console.error("❌ API nás zablokovalo (Rate Limit) pro název:", query);
        }
        return null;
      }

      const data = (await response.json()) as { image_url?: string | null; imageUrl?: string | null };
      const result = data.imageUrl ?? data.image_url ?? null;
      console.log(`📥 [FE 3/4] Výsledek pro název '${query}':`, result);
      return result;
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
      console.log(`✅ [FE FastPath] Produkt '${productName ?? tag}' již má platnou URL ze skrapování: ${nextImage}`);
      return () => {
        isActive = false;
      };
    }

    const queries = resolveImageQueries(productName, tag, visualKey);
    console.log(`🔍 [FE 1/4] ProductVisual init pro '${productName ?? tag}'. Seznam vyřešených kandidátů:`, queries);

    void (async () => {
      let image = await fetchProductImageByEan(ean, nextImage);

      if (!image) {
        for (const query of queries) {
          console.log(`👉 [FE Step] Zkouším candidate query: '${query}'`);
          image = await fetchProductImageByName(query, nextImage);
          if (image) {
            console.log(`🎯 [FE Match] Nalezen obrázek pro kandidáta '${query}' -> ${image}`);
            break;
          }
        }
      }

      if (!isActive) {
        return;
      }

      console.log(`🏁 [FE 4/4] Konečný stav pro '${productName ?? tag}':`, image ? `Obrázek ${image}` : "Zobrazuji Placeholder");
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
      onError={() => {
        console.warn(`❌ [FE Img Error] Obrázek selhal při načítání v prohlížeči (404/CORS): ${resolvedImage}`);
        setImageFailed(true);
      }}
      className={`${sizeClass} shrink-0 rounded-lg bg-stone-100 object-cover`}
    />
  );
}