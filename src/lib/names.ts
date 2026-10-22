// Docker-style random cluster names (<adjective>-<bread>) and the names derived from them
import { loadState } from "./state.js";

const ADJECTIVES = [
  "crusty", "fluffy", "golden", "toasty", "flaky", "buttery", "warm", "rustic",
  "sweet", "sourdough", "airy", "crispy", "tender", "honeyed", "malty", "seeded",
];
const BREADS = [
  "baguette", "croissant", "brioche", "bagel", "pretzel", "ciabatta", "focaccia", "scone",
  "muffin", "challah", "pita", "naan", "bun", "loaf", "roll", "danish",
];

export function randomClusterName(rand: () => number = Math.random): string {
  const pick = (list: string[]) => list[Math.floor(rand() * list.length)];
  return `${pick(ADJECTIVES)}-${pick(BREADS)}`;
}

export function isBakeryClusterName(name: string): boolean {
  const [adj, bread, ...rest] = name.split("-");
  return rest.length === 0 && ADJECTIVES.includes(adj) && BREADS.includes(bread);
}

export function clusterName(): string {
  return loadState().clusterName;
}

export function registryHost(): string {
  return `${clusterName()}-control-plane:30001`;
}
