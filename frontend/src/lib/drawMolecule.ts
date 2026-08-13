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

/** Draw a SMILES string into the given SVG element. */
export function drawMoleculeToSvg(smiles: string, svgElement: SVGSVGElement): DrawResult {
  try {
    const graph = SmilesDrawer.Parser.parse(smiles);
    const drawer = new SmilesDrawer.SvgDrawer({ width: 320, height: 240, compactDrawing: false });
    drawer.draw(graph, svgElement, "light", false);
    return { ok: true };
  } catch {
    return { ok: false, error: "Could not render a 2D depiction for this structure." };
  }
}
