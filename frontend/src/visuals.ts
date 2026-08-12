export type VisualSource = {
  label: string;
  localSrc: string;
  remoteQuery: string;
};

export const VISUAL_SOURCES: Record<string, VisualSource> = {
  vejce: { label: "Vejce", localSrc: "/food/vejce.jpg", remoteQuery: "eggs breakfast" },
  cola: { label: "Cola", localSrc: "/food/cola.jpg", remoteQuery: "cola soda can" },
  kureci: { label: "Kuřecí maso", localSrc: "/food/kureci-maso.jpg", remoteQuery: "chicken meat" },
  panenka: { label: "Panenka", localSrc: "/food/panenka.jpg", remoteQuery: "pork tenderloin" },
  brambory: { label: "Brambory", localSrc: "/food/brambory.jpg", remoteQuery: "potatoes" },
  banany: { label: "Banány", localSrc: "/food/banany.jpg", remoteQuery: "bananas fruit" },
  meloun: { label: "Meloun", localSrc: "/food/meloun.jpg", remoteQuery: "watermelon fruit" },
  broskve: { label: "Broskve", localSrc: "/food/broskve.jpg", remoteQuery: "peaches fruit" },
  nektarinky: { label: "Nektarinky", localSrc: "/food/nektarinky.jpg", remoteQuery: "nectarines fruit" },
  hrozny: { label: "Hrozny", localSrc: "/food/hrozny.jpg", remoteQuery: "grapes fruit" },
  ovoce: { label: "Ovoce", localSrc: "/food/ovoce.jpg", remoteQuery: "mixed fruit" },
  zelenina: { label: "Zelenina", localSrc: "/food/zelenina.jpg", remoteQuery: "fresh vegetables" },
  paprika: { label: "Paprika", localSrc: "/food/paprika.jpg", remoteQuery: "bell pepper" },
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