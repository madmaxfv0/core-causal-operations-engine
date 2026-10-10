/**
 * Well marker colours.
 *
 * These encode the AER-reported well category — a factual classification from the
 * ST37 record — not a computed risk score. Kept in its own module so the map page
 * can render the legend without pulling in the (lazily loaded) MapLibre bundle.
 */
export const WELL_COLOURS: [string, string][] = [
  ["Oil", "#5CC489"],
  ["Gas", "#4F6BE8"],
  ["Crude bitumen", "#F2B632"],
  ["Injection", "#5AC8E0"],
  ["Disposal", "#B7C4FF"],
  ["Observation", "#8E9AAF"],
  ["Not reported", "#6B7488"],
];

export type Basemap = "dark" | "satellite" | "streets" | "none";
