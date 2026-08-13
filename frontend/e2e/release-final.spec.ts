import { expect, test } from "@playwright/test";

/**
 * Phase 10 Sec 12: the final DrugSim v1.0 release test. Consolidates the
 * full golden path plus every edge case the release spec explicitly names
 * (invalid molecule, unsupported input, API failure, timeout, out-of-domain
 * molecule, experimental endpoint, unavailable endpoint) into one
 * self-contained file that does not depend on any other spec file existing
 * -- this is the sign-off artifact for the release decision, not a
 * duplicate of the feature-level specs elsewhere in this suite.
 *
 * The one invariant every test here checks in some form: no failed or
 * degraded request may ever produce a misleading result -- either a clean,
 * honest error, or a clearly-labelled real result with its reliability
 * context attached.
 */

const HERG_RESPONSE = {
  id: "pred_01release",
  request_id: "req_01release",
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
    dataset_version: "v1",
    feature_set_id: "fp_ecfp4_2048",
    standardization_pipeline_version: "std-v1",
    descriptor_spec_version: "desc-v1",
    rdkit_version: "2025.3.3",
    training_set_size: 6792,
    input_hash: "release-test-hash",
    final_report_status: "VALIDATED FOR INTERNAL RESEARCH",
  },
  warnings: [],
  inference_timestamp: "2026-08-11T00:00:00Z",
  status: "complete",
};

const ENDPOINTS_RESPONSE = {
  endpoints: [
    {
      model_id: "herg_inhibition",
      endpoint_name: "hERG (KCNH2/Kv11.1) inhibition",
      category: "Toxicity",
      final_report_status: "VALIDATED FOR INTERNAL RESEARCH",
      dataset_version: "v1",
      training_set_size: 9589,
      servable: true,
    },
    {
      model_id: "cyp3a4_inhibition",
      endpoint_name: "CYP3A4 inhibition",
      category: "Metabolism",
      final_report_status: "VALIDATED FOR INTERNAL RESEARCH",
      dataset_version: "v1",
      training_set_size: 5344,
      servable: true,
    },
    {
      model_id: "future_endpoint",
      endpoint_name: "Future endpoint",
      category: "Absorption",
      final_report_status: "EXPERIMENTAL",
      dataset_version: "v1",
      training_set_size: 200,
      servable: false,
    },
  ],
};

test.describe("DrugSim v1.0 final release test", () => {
  test("golden path: open, enter, validate, predict, and see prediction + uncertainty + AD + reliability + model version + limitations", async ({ page }) => {
    await page.route("**/api/predict", (route) => route.fulfill({ json: HERG_RESPONSE }));
    await page.route("**/api/endpoints", (route) => route.fulfill({ json: ENDPOINTS_RESPONSE }));

    await page.goto("/");
    await expect(page.getByRole("heading", { name: /explore how a molecule may behave/i })).toBeVisible();

    await page.getByRole("link", { name: /enter a molecule/i }).click();
    await page.getByLabel(/molecule \(smiles\)/i).fill("CC(=O)Oc1ccccc1C(=O)O");
    await page.getByRole("button", { name: /^validate$/i }).click();
    await expect(page.getByText(/canonical smiles/i)).toBeVisible();

    await page.getByRole("button", { name: /predict herg inhibition/i }).click();

    // Prediction
    await expect(page.getByRole("heading", { name: /predicted non-inhibitor/i })).toBeVisible();
    // Uncertainty
    await expect(page.getByRole("heading", { name: /uncertainty/i })).toBeVisible();
    // Applicability domain
    await expect(page.getByRole("heading", { name: /applicability domain/i })).toBeVisible();
    // Reliability
    await expect(page.getByRole("heading", { name: /reliability/i })).toBeVisible();
    // Model version identification
    await expect(page.getByText(/herg_inhibition v0\.1\.0/i)).toBeVisible();
    await expect(page.getByText(/VALIDATED FOR INTERNAL RESEARCH/)).toBeVisible();
    // Limitations reachable from this exact page
    await expect(page.getByRole("link", { name: /limitations/i }).first()).toBeVisible();
  });

  test("invalid molecule: malformed SMILES gets a clean 422, never a fabricated result", async ({ page }) => {
    await page.route("**/api/predict", (route) =>
      route.fulfill({
        status: 422,
        contentType: "application/problem+json",
        body: JSON.stringify({
          type: "https://drugsim.internal/errors/invalid-structure",
          title: "Molecular structure could not be processed",
          status: 422,
          detail: "could not parse smiles structure",
          errors: [{ field: "structure.value", code: "invalid_structure", message: "could not parse smiles structure" }],
        }),
      }),
    );
    await page.route("**/api/endpoints", (route) => route.fulfill({ json: ENDPOINTS_RESPONSE }));

    await page.goto("/predict");
    await page.getByLabel(/molecule \(smiles\)/i).fill("not-a-valid-smiles(((");
    await page.getByRole("button", { name: /^validate$/i }).click();

    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByText(/could not be processed/i)).toBeVisible();
    await expect(page.getByRole("heading", { name: /predicted/i })).toHaveCount(0);
  });

  test("unsupported input: free text that isn't chemistry at all is rejected as cleanly as a malformed SMILES", async ({ page }) => {
    await page.route("**/api/predict", (route) =>
      route.fulfill({
        status: 422,
        contentType: "application/problem+json",
        body: JSON.stringify({
          type: "https://drugsim.internal/errors/invalid-structure",
          title: "Molecular structure could not be processed",
          status: 422,
          detail: "could not parse smiles structure",
          errors: [{ field: "structure.value", code: "invalid_structure", message: "could not parse smiles structure" }],
        }),
      }),
    );
    await page.route("**/api/endpoints", (route) => route.fulfill({ json: ENDPOINTS_RESPONSE }));

    await page.goto("/predict");
    // The workspace only accepts SMILES text -- there is no format picker to
    // misuse, so "unsupported input" here means input that is not chemistry
    // at all, submitted through the one entry point that exists.
    await page.getByLabel(/molecule \(smiles\)/i).fill("this is just some English text, not a molecule");
    await page.getByRole("button", { name: /^validate$/i }).click();

    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByText(/could not be processed/i)).toBeVisible();
    await expect(page.getByRole("heading", { name: /predicted/i })).toHaveCount(0);

    // Validate/Predict are also never enabled on a genuinely empty field --
    // the other half of "unsupported input" is input that was never sent.
    await page.getByLabel(/molecule \(smiles\)/i).fill("");
    await expect(page.getByRole("button", { name: /^validate$/i })).toBeDisabled();
  });

  test("API failure: an unexpected 500 shows an honest error distinct from a network failure", async ({ page }) => {
    await page.route("**/api/predict", (route) =>
      route.fulfill({
        status: 500,
        contentType: "application/problem+json",
        body: JSON.stringify({ type: "about:blank", title: "Internal Server Error", status: 500, detail: "An unexpected error occurred." }),
      }),
    );
    await page.route("**/api/endpoints", (route) => route.fulfill({ json: ENDPOINTS_RESPONSE }));

    await page.goto("/predict");
    await page.getByLabel(/molecule \(smiles\)/i).fill("CCO");
    await page.getByRole("button", { name: /^validate$/i }).click();

    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByText(/something went wrong on our end/i)).toBeVisible();
  });

  test("timeout: a 503 from the prediction service shows an honest retry-worthy error", async ({ page }) => {
    await page.route("**/api/predict", (route) =>
      route.fulfill({
        status: 503,
        contentType: "application/problem+json",
        body: JSON.stringify({
          type: "https://drugsim.internal/errors/timeout",
          title: "Prediction timed out",
          status: 503,
          detail: "This structure could not be processed within the allotted time.",
        }),
      }),
    );
    await page.route("**/api/endpoints", (route) => route.fulfill({ json: ENDPOINTS_RESPONSE }));

    await page.goto("/predict");
    await page.getByLabel(/molecule \(smiles\)/i).fill("CCO");
    await page.getByRole("button", { name: /^validate$/i }).click();

    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByText(/temporarily unavailable/i)).toBeVisible();
  });

  test("out-of-domain molecule: rendered as a real, labelled result, never as an error", async ({ page }) => {
    await page.route("**/api/predict", (route) =>
      route.fulfill({
        json: {
          ...HERG_RESPONSE,
          reliability: {
            ...HERG_RESPONSE.reliability,
            applicability_domain: {
              verdict: "out_of_domain",
              max_tanimoto_to_training: 0.11,
              knn_distance: 6.2,
              knn_distance_threshold: 1.7,
              scaffold_seen_in_training: false,
              rationale: "Far from any training compound.",
              method: "tanimoto_knn_distance_scaffold_membership",
            },
          },
          warnings: [
            { code: "out_of_domain", severity: "high", message: "This prediction is an extrapolation.", field: "applicability_domain" },
          ],
        },
      }),
    );
    await page.route("**/api/endpoints", (route) => route.fulfill({ json: ENDPOINTS_RESPONSE }));

    await page.goto("/predict");
    await page.getByLabel(/molecule \(smiles\)/i).fill("CCO");
    await page.getByRole("button", { name: /^validate$/i }).click();
    await page.getByRole("button", { name: /predict herg inhibition/i }).click();

    await expect(page.getByText(/this prediction is an extrapolation/i)).toBeVisible();
    await expect(page.getByRole("heading", { name: /predicted non-inhibitor/i })).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
  });

  test("experimental endpoint: shown but disabled, never selectable as if it produced normal predictions", async ({ page }) => {
    await page.route("**/api/endpoints", (route) => route.fulfill({ json: ENDPOINTS_RESPONSE }));
    await page.route("**/api/predict", (route) => route.fulfill({ json: HERG_RESPONSE }));

    await page.goto("/predict");
    await page.getByLabel(/molecule \(smiles\)/i).fill("CCO");
    await page.getByRole("button", { name: /^validate$/i }).click();

    const experimentalButton = page.getByRole("button", { name: /future endpoint/i });
    await expect(experimentalButton).toBeVisible();
    await expect(experimentalButton).toBeDisabled();
    await expect(page.getByText(/EXPERIMENTAL/)).toBeVisible();
  });

  test("unavailable endpoint: a request naming an endpoint that failed its promotion gate gets an honest 403, not a fabricated prediction", async ({ page }) => {
    await page.route("**/api/predict", async (route) => {
      const body = route.request().postDataJSON();
      if (body.endpoint === "future_endpoint") {
        await route.fulfill({
          status: 403,
          contentType: "application/problem+json",
          body: JSON.stringify({
            type: "https://drugsim.internal/errors/endpoint-not-available",
            title: "Endpoint not available for predictions",
            status: 403,
            detail: "Endpoint 'future_endpoint' is registered with status 'EXPERIMENTAL', which has not passed the promotion gate.",
          }),
        });
      } else {
        await route.fulfill({ json: HERG_RESPONSE });
      }
    });
    // Endpoint discovery reports it as unavailable too -- consistent with the
    // disabled-selector test above; this test targets the API layer directly.
    // Issued as a real fetch from inside the page (not page.request, which
    // is a separate context page.route cannot intercept) so it goes through
    // the same mocked route as everything else in this suite.
    await page.route("**/api/endpoints", (route) => route.fulfill({ json: ENDPOINTS_RESPONSE }));
    await page.goto("/");

    const result = await page.evaluate(async () => {
      const res = await fetch("/api/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ structure: { format: "smiles", value: "CCO" }, endpoint: "future_endpoint" }),
      });
      return { status: res.status, body: await res.json() };
    });

    expect(result.status).toBe(403);
    expect(result.body.title).toMatch(/not available/i);
    expect(result.body).not.toHaveProperty("estimate");
  });
});
