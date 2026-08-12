// Small colored dot as a store identifier. kupiapi gives us shop names as
// text only, never a logo, so this is a deliberate stand-in rather than a
// missing feature - swap STORE_COLORS for real logos if you get a source
// for them later.

const STORE_COLORS: Record<string, string> = {
  lidl: "#0050AA",
  penny: "#E2001A",
  billa: "#C8102E",
  albert: "#00953B",
};

const FALLBACK_COLOR = "#a8a29e";

export function storeColor(storeId: string | null): string {
  return (storeId && STORE_COLORS[storeId]) || FALLBACK_COLOR;
}

interface StoreIconProps {
  storeId: string | null;
}

export function StoreIcon({ storeId }: StoreIconProps) {
  return (
    <span
      className="inline-block h-2 w-2 rounded-full"
      style={{ backgroundColor: storeColor(storeId) }}
    />
  );
}
