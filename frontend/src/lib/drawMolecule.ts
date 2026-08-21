/**
 * Client-side 2D structure depiction ONLY — no chemistry computation.
 *
 * smiles-drawer parses a SMILES string purely to lay out 2D coordinates for
 * display; it computes no descriptors, properties, or predictions. All
 * chemistry (standardisation, canonicalisation, feature generation) happens
 * server-side in drugsim_chem, exactly once (Phase 5). This module renders
 * whatever canonical structure the backend already returned.
 */
import SmilesDrawer from "smiles-drawer";

export interface DrawResult {
  ok: boolean;
  error?: string;
}

//: smiles-drawer's own diverging-colormap convention (SvgWrapper.drawWeights):
//: cmap[0] is the colour for a negative weight, cmap[last] for a positive
//: one -- reusing this app's existing concern/signal tokens rather than the
//: library's green/magenta default, so an explainability heatmap reads as
//: part of DrugSim rather than a bolted-on third-party widget.
const WEIGHT_COLORMAP = ["#1c6e6e", "#8b3a3a"]; // [decreases risk (signal), increases risk (concern)]

/** Draw a SMILES string into the given SVG element. `weights`, if given, is
 * one number per heavy atom (same order RDKit assigns them, i.e. the order
 * ExplainabilityResponse.atom_contributions already uses) -- rendered as a
 * red/teal heatmap. Library auto-scales by the largest-magnitude weight, so
 * raw SHAP contributions are passed through unnormalised. */
export function drawMoleculeToSvg(
  smiles: string,
  svgElement: SVGSVGElement,
  options?: { weights?: number[] },
): DrawResult {
  try {
    const graph = SmilesDrawer.Parser.parse(smiles);
    const drawer = new SmilesDrawer.SvgDrawer({
      width: 320,
      height: 240,
      compactDrawing: false,
      experimentalWeights: true,
      weights: { colormap: WEIGHT_COLORMAP, opacity: 0.6, sigma: 14 },
    });
    drawer.draw(graph, svgElement, "light", options?.weights ?? false);
    return { ok: true };
  } catch {
    return { ok: false, error: "Could not render a 2D depiction for this structure." };
  }
}
