import { useEffect, useState } from "react";
import type { ImageLookupMode } from "../api/client";

const STORAGE_KEY = "image-lookup-mode";

function readMode(): ImageLookupMode {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "quality" ? "quality" : "legacy";
  } catch {
    return "legacy";
  }
}

export function useImageLookupMode() {
  const [mode, setMode] = useState<ImageLookupMode>(readMode);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      // The current selection still works for this page if storage is unavailable.
    }
  }, [mode]);

  return [mode, setMode] as const;
}
