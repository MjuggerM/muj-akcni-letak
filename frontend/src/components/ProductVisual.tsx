import { useEffect, useState } from "react";

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
      const response = await fetch(
        `https://world.openfoodfacts.org/api/v2/search?code=${encodeURIComponent(normalizedEan)}&fields=product_name,image_front_url,image_url`
      );

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

      const data = JSON.parse(rawText) as {
        products?: Array<{ image_front_url?: string | null; image_url?: string | null }>;
      };

      const product = data.products?.[0];
      return product?.image_front_url ?? product?.image_url ?? null;
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
      await new Promise((resolve) => setTimeout(resolve, Math.random() * 2000));

      const response = await fetch(`http://localhost:8000/api/proxy-image?query=${encodeURIComponent(query)}`);

      if (!response.ok) {
        if (response.status === 429) {
          console.error("❌ API nás zablokovalo (Rate Limit) pro název:", query);
        }
        return null;
      }

      const data = (await response.json()) as { image_url?: string | null };
      return data.image_url ?? null;
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
  void visualKey;
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

    const sourceName = productName ?? tag ?? null;

    void (async () => {
      const image = (await fetchProductImageByEan(ean, nextImage)) ?? (await fetchProductImageByName(sourceName, nextImage));

      if (!isActive) {
        return;
      }

      setResolvedImage(image ?? null);
      setIsFetching(false);
    })();

    return () => {
      isActive = false;
    };
  }, [imageUrl, productName, tag]);

  if (isFetching || !resolvedImage || imageFailed) {
    return null;
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
