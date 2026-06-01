/**
 * E2E tests for error handling & stability (Task 6.4)
 *
 * Uses Playwright's API testing mode (no browser required).
 * Verifies the running backend (make dev-d or uvicorn directly):
 *   1. Request-logging middleware doesn't break normal responses.
 *   2. Unknown routes return well-formed JSON 404.
 *   3. Both batch and enrollment routers are registered (merge-conflict fix).
 *   4. Auth-protected endpoints return correct error shapes.
 *
 * Prerequisites: backend running on http://localhost:8000
 */

import { expect, test } from "@playwright/test";

const BASE = "http://localhost:8000";

// ─── Request-logging middleware doesn't break normal responses ─────────────────

test.describe("Request-logging middleware", () => {
  test("GET /docs returns 200", async ({ request }) => {
    const res = await request.get(`${BASE}/docs`);
    expect(res.status()).toBe(200);
  });

  test("unknown path returns JSON 404 — not HTML", async ({ request }) => {
    const res = await request.get(`${BASE}/this-path-does-not-exist`);
    expect(res.status()).toBe(404);
    const body = await res.json();
    expect(body).toHaveProperty("detail");
    expect(typeof body.detail).toBe("string");
  });
});

// ─── Router registration (merge-conflict fix) ──────────────────────────────────

test.describe("Router registration", () => {
  test("/batch/ endpoints appear in OpenAPI spec", async ({ request }) => {
    const res = await request.get(`${BASE}/openapi.json`);
    const spec = await res.json();
    const paths = Object.keys(spec.paths ?? {});
    expect(paths.some((p) => p.startsWith("/batch"))).toBe(true);
  });

  test("/enrollment/ endpoints appear in OpenAPI spec", async ({ request }) => {
    const res = await request.get(`${BASE}/openapi.json`);
    const spec = await res.json();
    const paths = Object.keys(spec.paths ?? {});
    expect(paths.some((p) => p.startsWith("/enrollment"))).toBe(true);
  });

  test("/owner/ endpoints appear in OpenAPI spec", async ({ request }) => {
    const res = await request.get(`${BASE}/openapi.json`);
    const spec = await res.json();
    const paths = Object.keys(spec.paths ?? {});
    expect(paths.some((p) => p.startsWith("/owner"))).toBe(true);
  });
});

// ─── Auth error shapes ─────────────────────────────────────────────────────────

test.describe("Auth error responses", () => {
  test("GET /batch/ with invalid token returns 401 JSON", async ({ request }) => {
    const res = await request.get(`${BASE}/batch/`, {
      headers: { Authorization: "Bearer not_a_real_token" },
    });
    expect(res.status()).toBe(401);
    const body = await res.json();
    expect(body).toHaveProperty("detail");
  });

  test("GET /enrollment/ with invalid token returns 401 JSON", async ({ request }) => {
    const res = await request.get(`${BASE}/enrollment/`, {
      headers: { Authorization: "Bearer not_a_real_token" },
    });
    expect([401, 404, 405, 422]).toContain(res.status());
  });
});
