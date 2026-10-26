import { useEffect, useState } from "react";
import { lookupImage } from "../api/imageLookup";
import type { ImageLookupMode } from "../api/client";
import { VISUAL_SOURCES } from "../visuals";

interface ProductVisualProps {
  imageUrl: string | null;
  tag: string;
  visualKey?: string | null;
  productName: string | null;
  imageLookupMode: ImageLookupMode;
  size?: "card" | "hit" | "full";
}

function isValidImageUrl(value: string | null | undefined): value is string {
  return Boolean(value && /^https?:\/\//i.test(value));
}

function normalizeName(value: string | null | undefined) {
  return (value ?? "").trim().replace(/\s+/g, " ");
}

function Placeholder({ label, sizeClass, fullSize }: { label: string; sizeClass: string; fullSize: boolean }) {
  return (
    <div
      aria-hidden="true"
      className={`${sizeClass} ${fullSize ? "flex items-center justify-center overflow-hidden bg-white p-4 text-center text-xs font-semibold leading-tight text-slate-500" : "flex shrink-0 items-center justify-center overflow-hidden rounded-xl bg-slate-100 p-1 text-center text-[10px] font-bold uppercase leading-tight tracking-[0.12em] text-slate-600 ring-1 ring-slate-200"}`}
    >
      {label}
    </div>
  );
}

export function ProductVisual({ imageUrl, tag, visualKey, productName, imageLookupMode, size = "card" }: ProductVisualProps) {
  const [resolvedImage, setResolvedImage] = useState<string | null>(isValidImageUrl(imageUrl) ? imageUrl : null);
  const [imageFailed, setImageFailed] = useState(false);
  const fullSize = size === "full";
  const sizeClass = fullSize ? "h-full w-full" : size === "hit" ? "h-14 w-14" : "h-16 w-16";

  useEffect(() => {
    let isActive = true;
    setImageFailed(false);

    if (isValidImageUrl(imageUrl)) {
      setResolvedImage(imageUrl);
      return () => {
        isActive = false;
      };
    }

    setResolvedImage(null);

    // Fotka se hledá VÝHRADNĚ podle přesného názvu produktu. Žádný záložní dotaz podle sledovaného
    // hesla ("paprika") ani podle obecné kategorie (visuals.ts): právě to způsobovalo, že koření
    // dostalo fotku zeleniny a různé produkty sdílely tutéž fotku. Když backend nenajde TENTO produkt,
    // je poctivé ukázat placeholder, ne odhad.
    const name = normalizeName(productName);
    if (name) {
      void lookupImage(name, imageLookupMode).then((outcome) => {
        if (isActive && outcome.kind === "found") setResolvedImage(outcome.url);
      });
    }

    return () => {
      isActive = false;
    };
  }, [imageUrl, productName, imageLookupMode]);

  if (!resolvedImage || imageFailed) {
    // tag/visualKey slouží jen jako TEXT na placeholderu - nikdy k výběru fotky.
    const label = (productName || tag || (visualKey ? VISUAL_SOURCES[visualKey]?.label : "") || "foto").slice(0, 12);
    return <Placeholder label={label} sizeClass={sizeClass} fullSize={fullSize} />;
  }

  return (
    <img
      src={resolvedImage}
      alt={productName ?? tag}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setImageFailed(true)}
      className={`${sizeClass} ${fullSize ? "object-contain w-full h-full p-2" : "aspect-square shrink-0 rounded-xl bg-white p-1.5 object-contain ring-1 ring-slate-200"}`}
    />
  );
}
