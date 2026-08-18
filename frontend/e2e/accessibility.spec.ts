import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/**
 * Automated WCAG 2.1 AA scan (axe-core) across every page, including the
 * prediction workspace in its populated (results-visible) state -- not
 * just the empty shell. This is Phase 7 hardening: Phase 6 built
 * accessible markup by hand (skip link, aria-live regions, focus rings,
 * labelled inputs) but never ran an automated scan to verify it.
 */
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
    training_set_size: 6792, input_hash: "3b139ddd2a92",
    final_report_status: "VALIDATED FOR INTERNAL RESEARCH",
  },
  warnings: [], inference_timestamp: "2026-08-09T00:00:00Z", status: "complete",
};

const ENDPOINTS_RESPONSE = {
  endpoints: [
    {
      model_id: "herg_inhibition", endpoint_name: "hERG (KCNH2/Kv11.1) inhibition", category: "Toxicity",
      final_report_status: "VALIDATED FOR INTERNAL RESEARCH", dataset_version: "v1", training_set_size: 9589, servable: true,
    },
    {
      model_id: "cyp3a4_inhibition", endpoint_name: "CYP3A4 inhibition", category: "Metabolism",
      final_report_status: "VALIDATED FOR INTERNAL RESEARCH", dataset_version: "v1", training_set_size: 5344, servable: true,
    },
    {
      model_id: "future_endpoint", endpoint_name: "Future endpoint", category: "Absorption",
      final_report_status: "EXPERIMENTAL", dataset_version: "v1", training_set_size: 200, servable: false,
    },
  ],
};

const CYP3A4_RESPONSE = {
  ...PREDICTION_RESPONSE,
  estimate: { endpoint: "cyp3a4_inhibition", predicted_label: "inhibitor", predicted_probability_blocker: null, predicted_probability: 0.71 },
  reliability: {
    conformal: {
      predicted_set: ["inhibitor"], p_value_blocker: 0.7, p_value_non_blocker: 0.02,
      nominal_confidence: 0.9, is_singleton: true, method: "split_conformal_prediction",
    },
    applicability_domain: PREDICTION_RESPONSE.reliability.applicability_domain,
  },
  provenance: { ...PREDICTION_RESPONSE.provenance, model_id: "cyp3a4_inhibition", training_set_size: 3767 },
};

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
];

for (const path of STATIC_PAGES) {
  test(`no WCAG 2.1 AA violations on ${path}`, async ({ page }) => {
    await page.goto(path);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });
}

test("no WCAG 2.1 AA violations on the populated results view", async ({ page }) => {
  await page.route("**/api/predict", async (route) => {
    await route.fulfill({ json: PREDICTION_RESPONSE });
  });
  await page.goto("/predict");
  await page.getByLabel(/paste a smiles string/i).fill("CC(=O)Oc1ccccc1C(=O)O");
  await page.getByRole("button", { name: /^validate$/i }).click();
  await page.getByRole("button", { name: /predict herg inhibition/i }).click();
  await expect(page.getByRole("heading", { name: /predicted non-inhibitor/i })).toBeVisible();
  // Also expand the collapsible "Model & evidence" panel -- its content
  // (checksums, version strings) only exists in the DOM once opened, so a
  // scan of the collapsed page alone would miss it entirely.
  await page.getByRole("button", { name: /model.*evidence/i }).click();
  await expect(page.getByText(PREDICTION_RESPONSE.provenance.model_checksum)).toBeVisible();

  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
});

test("no WCAG 2.1 AA violations on the endpoint selector, including its disabled experimental option", async ({ page }) => {
  await page.route("**/api/endpoints", (route) => route.fulfill({ json: ENDPOINTS_RESPONSE }));
  await page.goto("/predict");
  await expect(page.getByRole("button", { name: /future endpoint/i })).toBeVisible();

  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
});

test("no WCAG 2.1 AA violations on the DrugSim Compound Profile view (Phase 10)", async ({ page }) => {
  await page.route("**/api/endpoints", (route) => route.fulfill({ json: ENDPOINTS_RESPONSE }));
  await page.route("**/api/predict", async (route) => {
    const body = route.request().postDataJSON();
    await route.fulfill({ json: body.endpoint === "cyp3a4_inhibition" ? CYP3A4_RESPONSE : PREDICTION_RESPONSE });
  });

  await page.goto("/predict");
  await page.getByLabel(/paste a smiles string/i).fill("CC(=O)Oc1ccccc1C(=O)O");
  await page.getByRole("button", { name: /^validate$/i }).click();
  await page.getByRole("button", { name: /full compound profile/i }).click();
  await expect(page.getByRole("heading", { name: /every validated endpoint/i })).toBeVisible();
  await expect(page.getByText(/predicted non-inhibitor/i)).toBeVisible();
  await expect(page.getByText(/predicted cyp3a4 inhibitor/i)).toBeVisible();

  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
});

test("no WCAG 2.1 AA violations with an error state visible", async ({ page }) => {
  await page.route("**/api/predict", async (route) => {
    await route.fulfill({ status: 500, json: { type: "about:blank", title: "Internal Server Error", status: 500, detail: "boom" } });
  });
  await page.goto("/predict");
  await page.getByLabel(/paste a smiles string/i).fill("CCO");
  await page.getByRole("button", { name: /^validate$/i }).click();
  await expect(page.getByRole("alert")).toBeVisible();

  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
});
