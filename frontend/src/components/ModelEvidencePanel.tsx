import { useState } from "react";
import { Link } from "react-router-dom";
import type { PredictionResponse } from "../api/types";

interface Props {
  prediction: PredictionResponse;
}

/** Collapsible "Model & Evidence" panel — full scientific provenance,
 * available without overwhelming the primary results view. */
export function ModelEvidencePanel({ prediction }: Props) {
  const [open, setOpen] = useState(false);
  const { provenance, reliability } = prediction;
  const { applicability_domain, conformal } = reliability;

  return (
    <div className="rounded-lg border border-line">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls="model-evidence-content"
        className="flex w-full items-center justify-between px-5 py-4 text-left"
      >
        <span className="font-medium text-ink">Model &amp; evidence</span>
        <span className="text-ink-soft" aria-hidden="true">
          {open ? "−" : "+"}
        </span>
      </button>
      {open && (
        <div id="model-evidence-content" className="border-t border-line px-5 py-4">
          <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
            <Field label="Model">
              {provenance.model_id} v{provenance.model_version}
            </Field>
            <Field label="Status">{provenance.final_report_status}</Field>
            <Field label="Endpoint">{prediction.estimate.endpoint}</Field>
            <Field label="Dataset version">{provenance.dataset_version}</Field>
            <Field label="Training-set size">{provenance.training_set_size.toLocaleString()} compounds</Field>
            <Field label="Feature-set ID">
              <span className="font-mono text-xs break-all">{provenance.feature_set_id}</span>
            </Field>
            <Field label="Model checksum (SHA-256)">
              <span className="font-mono text-xs break-all">{provenance.model_checksum}</span>
            </Field>
            <Field label="Standardisation pipeline version">{provenance.standardization_pipeline_version}</Field>
            <Field label="Descriptor spec version">{provenance.descriptor_spec_version}</Field>
            <Field label="RDKit version">{provenance.rdkit_version}</Field>
            <Field label="Applicability-domain method">
              Max Tanimoto similarity + k-NN descriptor distance + scaffold-seen, combined
            </Field>
            <Field label="Uncertainty method">Split conformal prediction</Field>
            <Field label="k-NN distance">
              {applicability_domain.knn_distance !== null
                ? `${applicability_domain.knn_distance.toFixed(2)} (threshold ${applicability_domain.knn_distance_threshold.toFixed(2)})`
                : "not available"}
            </Field>
            <Field label="Conformal nominal confidence">{Math.round(conformal.nominal_confidence * 100)}%</Field>
            <Field label="Input hash">
              <span className="font-mono text-xs break-all">{provenance.input_hash}</span>
            </Field>
          </dl>
          <p className="mt-4 text-xs leading-relaxed text-ink-soft">
            These identifiers, together with the timestamp below, are everything needed to
            reproduce this exact prediction: which model binary, which chemistry/feature
            toolchain, and which submitted structure (by its non-reversible hash) produced it.
          </p>
          <p className="mt-4 text-sm text-ink-soft">
            Full validation methodology, leakage checks, external validation, and known
            limitations are documented in the{" "}
            <Link to="/methodology" className="underline underline-offset-2 hover:text-ink">
              methodology page
            </Link>{" "}
            and the project's Phase 3–4 reliability reports.
          </p>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">{label}</dt>
      <dd className="mt-1 text-sm text-ink">{children}</dd>
    </div>
  );
}
