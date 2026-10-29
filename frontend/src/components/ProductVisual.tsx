import { useEffect, useState } from "react";
import { lookupImage } from "../api/imageLookup";
import type { ImageLookupMode } from "../api/client";

interface ProductVisualProps {
  imageUrl: string | null;
  tag: string;
  productName: string | null;
  imageLookupMode: ImageLookupMode;
}

function isValidImageUrl(value: string | null | undefined): value is string {
  return Boolean(value && /^https?:\/\//i.test(value));
}

function normalizeName(value: string | null | undefined) {
  return (value ?? "").trim().replace(/\s+/g, " ");
}

function Placeholder({ label }: { label: string }) {
  return (
    <div
      aria-hidden="true"
      className="h-full w-full flex items-center justify-center overflow-hidden bg-white p-4 text-center text-xs font-semibold leading-tight text-slate-500"
    >
      {label}
    </div>
  );
}

export function ProductVisual({ imageUrl, tag, productName, imageLookupMode }: ProductVisualProps) {
  const [resolvedImage, setResolvedImage] = useState<string | null>(isValidImageUrl(imageUrl) ? imageUrl : null);
  const [imageFailed, setImageFailed] = useState(false);

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
    // hesla ("paprika") ani podle obecné kategorie: právě to způsobovalo, že koření
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
    // Hledaný výraz je jen text placeholderu; nikdy se podle něj nehledá fotka.
    const label = (productName || tag || "foto").slice(0, 12);
    return <Placeholder label={label} />;
  }

  return (
    <img
      src={resolvedImage}
      alt={productName ?? tag}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setImageFailed(true)}
      className="h-full w-full object-contain p-2"
    />
  );
}
