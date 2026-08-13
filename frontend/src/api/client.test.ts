import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, getPrediction, predict } from "./client";

describe("client error classification", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("classifies a 401 as unauthorized (Phase 8: API-key gate)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            type: "https://drugsim.internal/errors/unauthorized",
            title: "Missing or invalid API key",
            status: 401,
            detail: "This endpoint requires a valid X-API-Key header.",
          }),
          { status: 401 },
        ),
      ),
    );

    await expect(predict("CCO")).rejects.toMatchObject({ kind: "unauthorized" });
  });

  it("classifies a 429 as rate_limited (Phase 8: rate limiting)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ type: "about:blank", title: "Too many requests", status: 429, detail: "slow down" }), {
          status: 429,
        }),
      ),
    );

    await expect(predict("CCO")).rejects.toMatchObject({ kind: "rate_limited" });
  });
});

describe("client API key header (Phase 8)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("sends X-API-Key when VITE_API_KEY is configured at build time", async () => {
    vi.stubEnv("VITE_API_KEY", "test-key-123");
    vi.resetModules();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const freshClient = await import("./client");
    await freshClient.checkHealth();

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>)["X-API-Key"]).toBe("test-key-123");
  });

  it("omits X-API-Key when VITE_API_KEY is not configured", async () => {
    vi.stubEnv("VITE_API_KEY", "");
    vi.resetModules();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const freshClient = await import("./client");
    await freshClient.checkHealth();

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>)["X-API-Key"]).toBeUndefined();
  });
});

describe("client error classification (existing)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("classifies a 404 on getPrediction as not_found (missing prediction)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            type: "https://drugsim.internal/errors/not-found",
            title: "Prediction not found",
            status: 404,
            detail: "No completed prediction with id 'prd_doesnotexist'",
          }),
          { status: 404, headers: { "Content-Type": "application/problem+json" } },
        ),
      ),
    );

    await expect(getPrediction("prd_doesnotexist")).rejects.toMatchObject({
      kind: "not_found",
    } satisfies Partial<ApiError>);
  });

  it("classifies a 500 as server_error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ type: "about:blank", title: "Internal Server Error", status: 500, detail: "boom" }), {
          status: 500,
        }),
      ),
    );

    await expect(predict("CCO")).rejects.toMatchObject({ kind: "server_error" });
  });

  it("classifies a 503 as unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ type: "about:blank", title: "unavailable", status: 503, detail: "not ready" }), {
          status: 503,
        }),
      ),
    );

    await expect(predict("CCO")).rejects.toMatchObject({ kind: "unavailable" });
  });

  it("classifies a request that never resolves as a timeout, and aborts it", async () => {
    vi.useFakeTimers();
    let aborted = false;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            aborted = true;
            const err = new DOMException("The operation was aborted.", "AbortError");
            reject(err);
          });
        });
      }),
    );

    const resultPromise = predict("CCO");
    const assertion = expect(resultPromise).rejects.toMatchObject({ kind: "timeout" });
    await vi.advanceTimersByTimeAsync(15_000);
    await assertion;
    expect(aborted).toBe(true);
  });

  it("classifies a network failure (fetch throws) as network", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );

    await expect(predict("CCO")).rejects.toMatchObject({ kind: "network" });
  });
});
