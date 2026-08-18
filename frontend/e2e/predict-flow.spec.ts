import { expect, test } from "@playwright/test";

/**
 * End-to-end coverage of the core user flow (spec section 1): enter a
 * molecule, validate it, run a prediction, and see the result with its
 * uncertainty, applicability domain, and reliability always visible.
 *
 * The Phase 5 API call is stubbed at the network boundary with a response
 * shaped exactly like a real `/predict` response, so this test exercises
 * real frontend code (routing, state, rendering) against a fixed, known
 * contract — without depending on a live model/database in CI.
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
  estimate: {
    endpoint: "herg_inhibition",
    predicted_label: "non_blocker",
    predicted_probability_blocker: 0.12,
    predicted_probability: 0.12,
  },
  reliability: {
    conformal: {
      predicted_set: ["non_blocker"],
      p_value_blocker: 0.03,
      p_value_non_blocker: 0.62,
      nominal_confidence: 0.9,
      is_singleton: true,
      method: "split_conformal_prediction",
    },
    applicability_domain: {
      verdict: "in_domain",
      max_tanimoto_to_training: 0.82,
      knn_distance: 0.4,
      knn_distance_threshold: 0.6,
      scaffold_seen_in_training: true,
      rationale: "This structure closely resembles compounds seen during training.",
      method: "tanimoto_knn_distance_scaffold_membership",
    },
  },
  provenance: {
    model_id: "herg_inhibition",
    model_version: "0.1.0",
    model_checksum: "a".repeat(64),
    dataset_version: "2026.01",
    feature_set_id: "fp_ecfp4_2048",
    standardization_pipeline_version: "std-v1",
    descriptor_spec_version: "desc-v1",
    rdkit_version: "2025.3.3",
    training_set_size: 6792,
    input_hash: "3b139ddd2a92",
    final_report_status: "VALIDATED FOR INTERNAL RESEARCH",
  },
  warnings: [],
  inference_timestamp: "2026-08-09T00:00:00Z",
  status: "complete",
};

test("full input -> validate -> predict -> display flow", async ({ page }) => {
  await page.route("**/api/predict", async (route) => {
    await route.fulfill({ json: PREDICTION_RESPONSE });
  });

  await page.goto("/");
  await page.getByRole("link", { name: /enter a molecule/i }).click();

  await page.getByLabel(/paste a smiles string/i).fill("CC(=O)Oc1ccccc1C(=O)O");
  await page.getByRole("button", { name: /^validate$/i }).click();

  await expect(page.getByText(/canonical smiles/i)).toBeVisible();

  await page.getByRole("button", { name: /predict herg inhibition/i }).click();

  await expect(page.getByRole("heading", { name: /predicted non-inhibitor/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /uncertainty/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /applicability domain/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /reliability/i })).toBeVisible();
  await expect(page.getByText(/6,792 compounds/)).toBeVisible();
});

test("an optional compound name is shown alongside the result but never sent to the API", async ({ page }) => {
  let sentBody: Record<string, unknown> | undefined;
  await page.route("**/api/predict", async (route) => {
    sentBody = route.request().postDataJSON();
    await route.fulfill({ json: PREDICTION_RESPONSE });
  });

  await page.goto("/predict");
  await page.getByLabel(/compound name/i).fill("Aspirin");
  await page.getByLabel(/paste a smiles string/i).fill("CC(=O)Oc1ccccc1C(=O)O");
  await page.getByRole("button", { name: /^validate$/i }).click();

  // Shown in the molecule preview once validated (exact match, scoped to
  // the molecule region -- avoids the unrelated "Aspirin" example button
  // in the input form, which also contains the word).
  const moleculeSection = page.getByRole("region", { name: /^molecule$/i });
  await expect(moleculeSection.getByText("Aspirin", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: /predict herg inhibition/i }).click();

  // Shown again alongside the prediction result -- scoped to the molecule
  // preview and results regions specifically (not a page-wide count),
  // since the input form's own "Aspirin" example button also contains the
  // word and isn't part of what this test is checking.
  const resultsHeading = page.getByRole("heading", { name: /predicted non-inhibitor/i });
  await expect(resultsHeading).toBeVisible();
  const resultsSection = page.getByRole("region", { name: /predicted non-inhibitor/i });
  await expect(moleculeSection.getByText("Aspirin", { exact: true })).toBeVisible();
  await expect(resultsSection.getByText("Aspirin", { exact: true })).toBeVisible();
  // ...but never part of the actual request the backend receives.
  expect(sentBody).toBeDefined();
  expect(JSON.stringify(sentBody)).not.toContain("Aspirin");

  // Clearing the form clears the name too.
  await page.getByRole("button", { name: /^clear$/i }).click();
  await expect(page.getByLabel(/compound name/i)).toHaveValue("");
});

test("shows an honest error instead of a fabricated result on API failure", async ({ page }) => {
  await page.route("**/api/predict", async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/problem+json",
      body: JSON.stringify({
        type: "about:blank",
        title: "Internal Server Error",
        status: 500,
        detail: "An unexpected error occurred.",
      }),
    });
  });

  await page.goto("/predict");
  await page.getByLabel(/paste a smiles string/i).fill("CC(=O)Oc1ccccc1C(=O)O");
  await page.getByRole("button", { name: /^validate$/i }).click();

  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByText(/predicted non-inhibitor/i)).not.toBeVisible();
});

test("renders an out-of-domain prediction as a successful, informative result, not an error", async ({ page }) => {
  await page.route("**/api/predict", async (route) => {
    await route.fulfill({
      json: {
        ...PREDICTION_RESPONSE,
        reliability: {
          ...PREDICTION_RESPONSE.reliability,
          applicability_domain: {
            verdict: "out_of_domain",
            max_tanimoto_to_training: 0.12,
            knn_distance: 5.0,
            knn_distance_threshold: 1.7,
            scaffold_seen_in_training: false,
            rationale: "Far from any training compound.",
            method: "tanimoto_knn_distance_scaffold_membership",
          },
        },
        warnings: [
          {
            code: "out_of_domain",
            severity: "high",
            message: "This prediction is an extrapolation.",
            field: "applicability_domain",
          },
        ],
      },
    });
  });

  await page.goto("/predict");
  await page.getByLabel(/paste a smiles string/i).fill("CC(=O)Oc1ccccc1C(=O)O");
  await page.getByRole("button", { name: /^validate$/i }).click();
  await page.getByRole("button", { name: /predict herg inhibition/i }).click();

  await expect(page.getByText(/this prediction is an extrapolation/i)).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

/**
 * Phase 9 Sec 19 E2E requirement: molecule -> endpoint selection ->
 * prediction -> uncertainty -> applicability domain -> result display,
 * for a SECOND endpoint (not the hERG default). GET /endpoints is stubbed
 * with two registered endpoints so the selector actually has something to
 * choose between, and POST /predict is stubbed with a CYP3A4-shaped
 * response using CYP3A4's own label vocabulary -- exercising the real
 * endpoint-selection code path, not just the hERG default.
 */
const ENDPOINTS_RESPONSE = {
  endpoints: [
    {
      model_id: "herg_inhibition",
      endpoint_name: "hERG (KCNH2/Kv11.1) inhibition",
      category: null,
      final_report_status: "VALIDATED FOR INTERNAL RESEARCH",
      dataset_version: "v1",
      training_set_size: 9589,
      servable: true,
    },
    {
      model_id: "cyp3a4_inhibition",
      endpoint_name: "CYP3A4 inhibition",
      category: "Metabolism (ADMET)",
      final_report_status: "VALIDATED FOR INTERNAL RESEARCH",
      dataset_version: "v1",
      training_set_size: 5344,
      servable: true,
    },
    {
      model_id: "future_endpoint",
      endpoint_name: "Future endpoint",
      category: null,
      final_report_status: "EXPERIMENTAL",
      dataset_version: "v1",
      training_set_size: 500,
      servable: false,
    },
  ],
};

const CYP3A4_PREDICTION_RESPONSE = {
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

test("full molecule -> endpoint selection -> prediction -> reliability flow for a non-default endpoint", async ({ page }) => {
  await page.route("**/api/endpoints", async (route) => {
    await route.fulfill({ json: ENDPOINTS_RESPONSE });
  });
  await page.route("**/api/predict", async (route) => {
    const body = route.request().postDataJSON();
    if (body.endpoint === "cyp3a4_inhibition") {
      await route.fulfill({ json: CYP3A4_PREDICTION_RESPONSE });
    } else {
      await route.fulfill({ json: PREDICTION_RESPONSE });
    }
  });

  await page.goto("/predict");

  // The experimental, non-servable endpoint is shown but disabled -- never
  // silently hidden, never selectable as if it produced normal predictions.
  const futureButton = page.getByRole("button", { name: /future endpoint/i });
  await expect(futureButton).toBeVisible();
  await expect(futureButton).toBeDisabled();

  await page.getByRole("button", { name: /cyp3a4 inhibition/i }).click();
  await page.getByLabel(/paste a smiles string/i).fill("CC(=O)Oc1ccccc1C(=O)O");
  await page.getByRole("button", { name: /^validate$/i }).click();
  await page.getByRole("button", { name: /predict cyp3a4 inhibition/i }).click();

  await expect(page.getByRole("heading", { name: /predicted cyp3a4 inhibitor/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /uncertainty/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /applicability domain/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /reliability/i })).toBeVisible();
  await expect(page.getByText(/3,767 compounds/)).toBeVisible();
});
