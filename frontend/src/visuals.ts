export type VisualSource = {
  label: string;
  remoteQuery: string;
};

export const VISUAL_SOURCES: Record<string, VisualSource> = {
  vejce: { label: "Vejce", remoteQuery: "eggs breakfast" },
  cola: { label: "Cola", remoteQuery: "cola soda can" },
  kureci: { label: "Kuřecí maso", remoteQuery: "chicken meat" },
  panenka: { label: "Panenka", remoteQuery: "pork tenderloin" },
  brambory: { label: "Brambory", remoteQuery: "potatoes" },
  banany: { label: "Banány", remoteQuery: "bananas fruit" },
  meloun: { label: "Meloun", remoteQuery: "watermelon fruit" },
  broskve: { label: "Broskve", remoteQuery: "peaches fruit" },
  nektarinky: { label: "Nektarinky", remoteQuery: "nectarines fruit" },
  hrozny: { label: "Hrozny", remoteQuery: "grapes fruit" },
  ovoce: { label: "Ovoce", remoteQuery: "mixed fruit" },
  zelenina: { label: "Zelenina", remoteQuery: "fresh vegetables" },
  paprika: { label: "Paprika", remoteQuery: "bell pepper" },
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