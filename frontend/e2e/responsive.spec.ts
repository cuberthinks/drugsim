import { expect, test } from "@playwright/test";

/**
 * Phase 8 finding: every page had real horizontal overflow on a mobile
 * viewport (390x844, an iPhone-13-sized screen) -- the header nav didn't
 * wrap, and MoleculeStructure's SVG had fixed pixel width/height
 * attributes (set by smiles-drawer at draw time) that didn't shrink. Both
 * fixed; this pins the fix so it cannot silently regress.
 *
 * A plain viewport override, not the `devices["iPhone 13"]` preset --
 * that preset also pins the WebKit engine, which isn't installed in this
 * project's Playwright config (chromium only, see playwright.config.ts).
 * A custom viewport keeps this test on the same browser as the rest of
 * the suite while still exercising a real mobile width.
 */
test.use({ viewport: { width: 390, height: 844 } });

const STATIC_PAGES = [
  "/",
  "/predict",
  "/methodology",
  "/limitations",
  "/about",
  "/privacy",
  "/terms",
  "/history",
  "/compare",
  "/changelog",
  "/sources",
  "/benchmarks",
];

for (const path of STATIC_PAGES) {
  test(`no horizontal overflow on ${path} at mobile width`, async ({ page }) => {
    await page.goto(path);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
}

const PREDICTION_RESPONSE = {
  id: "pred_01e2e",
  request_id: "req_01e2e",
  molecule: {
    canonical_smiles: "CC(=O)Oc1ccccc1C(=O)O",
    isomeric_smiles: "CC(=O)Oc1ccccc1C(=O)O",
    standardized_smiles: "CC(=O)Oc1ccccc1C(=O)O",
    inchikey_full: "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
    molecular_formula: "C9H8O4",
  },
  estimate: { endpoint: "herg_inhibition", predicted_label: "non_blocker", predicted_probability_blocker: 0.12, predicted_probability: 0.12 },
  reliability: {
    conformal: {
      predicted_set: ["non_blocker"], p_value_blocker: 0.03, p_value_non_blocker: 0.62,
      nominal_confidence: 0.9, is_singleton: true, method: "split_conformal_prediction",
    },
    applicability_domain: {
      verdict: "in_domain", max_tanimoto_to_training: 0.82, knn_distance: 0.4,
      knn_distance_threshold: 0.6, scaffold_seen_in_training: true,
      rationale: "This structure closely resembles compounds seen during training.",
      method: "tanimoto_knn_distance_scaffold_membership",
    },
  },
  provenance: {
    model_id: "herg_inhibition", model_version: "0.1.0", model_checksum: "a".repeat(64),
    dataset_version: "2026.01", feature_set_id: "fp_ecfp4_2048",
    standardization_pipeline_version: "std-v1", descriptor_spec_version: "desc-v1", rdkit_version: "2025.3.3",
    training_set_size: 6792, input_hash: "abc123",
    final_report_status: "VALIDATED FOR INTERNAL RESEARCH",
  },
  warnings: [], inference_timestamp: "2026-08-09T00:00:00Z", status: "complete",
};

test("no horizontal overflow on the populated results view (with Model & evidence expanded) at mobile width", async ({ page }) => {
  await page.route("**/api/predict", async (route) => {
    await route.fulfill({ json: PREDICTION_RESPONSE });
  });
  await page.goto("/predict");
  await page.getByLabel(/paste a smiles string/i).fill("CC(=O)Oc1ccccc1C(=O)O");
  await page.getByRole("button", { name: /^validate$/i }).click();
  await page.getByRole("button", { name: /predict herg inhibition/i }).click();
  await expect(page.getByRole("heading", { name: /predicted non-inhibitor/i })).toBeVisible();
  await page.getByRole("button", { name: /model.*evidence/i }).click();
  await expect(page.getByText(PREDICTION_RESPONSE.provenance.model_checksum)).toBeVisible();

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
});
