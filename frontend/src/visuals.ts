export type VisualSource = {
  label: string;
};

export const VISUAL_SOURCES: Record<string, VisualSource> = {
  vejce: { label: "Vejce" },
  cola: { label: "Cola" },
  kureci: { label: "Kuřecí maso" },
  panenka: { label: "Panenka" },
  brambory: { label: "Brambory" },
  banany: { label: "Banány" },
  meloun: { label: "Meloun" },
  broskve: { label: "Broskve" },
  nektarinky: { label: "Nektarinky" },
  hrozny: { label: "Hrozny" },
  ovoce: { label: "Ovoce" },
  zelenina: { label: "Zelenina" },
  paprika: { label: "Paprika" },
};

export function normalizedVisualText(value: string) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

export function findVisualKey(value: string) {
  const text = normalizedVisualText(value);
  const patterns: Array<[RegExp, string]> = [
    [/vejce/, "vejce"], [/cola|coca/, "cola"], [/kureci|kure/, "kureci"], [/panenka/, "panenka"],
    [/brambor/, "brambory"], [/banan/, "banany"], [/meloun/, "meloun"], [/broskev/, "broskve"],
    [/nektar/, "nektarinky"], [/hrozn/, "hrozny"], [/paprik/, "paprika"], [/zelenin/, "zelenina"], [/ovoce/, "ovoce"],
  ];
  return patterns.find(([pattern]) => pattern.test(text))?.[1] ?? null;
}