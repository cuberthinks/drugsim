import { useEffect, useRef, useState } from "react";
import { drawMoleculeToSvg } from "../lib/drawMolecule";

interface MoleculeStructureProps {
  smiles: string;
  label?: string;
}

/** Renders a 2D depiction of an already-canonicalised SMILES string. Pure
 * presentation — see lib/drawMolecule.ts for why this does not count as
 * duplicating backend chemistry logic. */
export function MoleculeStructure({ smiles, label }: MoleculeStructureProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [renderError, setRenderError] = useState<string | null>(null);

  useEffect(() => {
    if (!svgRef.current) return;
    const result = drawMoleculeToSvg(smiles, svgRef.current);
    setRenderError(result.ok ? null : (result.error ?? "Rendering failed."));
  }, [smiles]);

  return (
    <div className="flex w-full flex-col items-center rounded-lg border border-line bg-white p-4">
      <svg
        ref={svgRef}
        role="img"
        aria-label={label ?? `2D structure depiction of ${smiles}`}
        width={320}
        height={240}
        viewBox="0 0 320 240"
        // Phase 8 responsive-layout fix: smiles-drawer sets pixel width/
        // height attributes on this element when it draws (matching the
        // {width:320, height:240} options in lib/drawMolecule.ts), which
        // does not shrink on a narrow viewport and caused real horizontal
        // page overflow on mobile. CSS overrides SVG presentation
        // attributes, so this class makes it responsive regardless of
        // what the drawing library sets on the element directly.
        className="h-auto w-full max-w-[320px]"
      />
      {renderError && (
        <p className="mt-2 text-xs text-ink-soft">
          {renderError} The canonical SMILES below is still authoritative.
        </p>
      )}
    </div>
  );
}
