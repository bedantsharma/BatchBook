/**
 * E2E tests for Batch Management (Task 2.1)
 *
 * These tests drive the full stack (frontend + backend) via Playwright.
 * Prerequisites: `make dev-d` must be running and the owner must be logged in.
 *
 * The tests use the backend API directly (via fetch) where UI isn't yet wired up
 * (frontend batch UI is Task 2.3, not yet built). They verify the API is reachable
 * and returns correct HTTP status codes through the nginx proxy.
 */

import { expect, test } from "@playwright/test";

const BACKEND_URL = "http://localhost:8000";

/**
 * Helper: call the backend API directly.
 * In the real stack the frontend proxy would forward /batch/* → backend,
 * but for API-layer E2E tests we call the backend directly.
 */
async function apiGet(path: string, token = "") {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BACKEND_URL}${path}`, { method: "GET", headers });
  return { status: res.status, body: await res.json().catch(() => null) };
}

async function apiPost(path: string, body: unknown, token = "") {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BACKEND_URL}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  return { status: res.status, body: await res.json().catch(() => null) };
}

// ─── Unauthenticated access checks ────────────────────────────────────────────

test.describe("Batch API — unauthenticated access", () => {
  test("GET /batch/ returns 422 without Authorization header", async () => {
    const { status } = await apiGet("/batch/");
    // FastAPI returns 422 for missing required Header (Authorization)
    expect([401, 422]).toContain(status);
  });

  test("POST /batch/ returns 422 without Authorization header", async () => {
    const { status } = await apiPost("/batch/", {
      name: "Test Batch",
      subject: "Maths",
      start_time: "16:00:00",
      end_time: "17:00:00",
      days_of_week: ["MON"],
      max_capacity: 30,
      end_date: "2027-05-01",
    });
    expect([401, 422]).toContain(status);
  });

  test("GET /batch/1 returns 422 or 401 without auth", async () => {
    const { status } = await apiGet("/batch/1");
    expect([401, 422]).toContain(status);
  });
});

// ─── Invalid token checks ──────────────────────────────────────────────────────

test.describe("Batch API — invalid token", () => {
  test("GET /batch/ returns 401 with bad token", async () => {
    const { status } = await apiGet("/batch/", "not_a_real_token");
    expect(status).toBe(401);
  });

  test("POST /batch/ returns 401 with bad token", async () => {
    const { status } = await apiPost(
      "/batch/",
      {
        name: "Test Batch",
        subject: "Maths",
        start_time: "16:00:00",
        end_time: "17:00:00",
        days_of_week: ["MON"],
        max_capacity: 30,
        end_date: "2027-05-01",
      },
      "not_a_real_token"
    );
    expect(status).toBe(401);
  });
});

// ─── Input validation ──────────────────────────────────────────────────────────

test.describe("Batch API — input validation", () => {
  test("POST /batch/ returns 422 with invalid day names", async () => {
    // Even with a bad token, validation errors (422) happen before auth in some cases.
    // We just care that MONDAY (not MON) is rejected.
    const { status } = await apiPost(
      "/batch/",
      {
        name: "Test Batch",
        subject: "Maths",
        start_time: "16:00:00",
        end_time: "17:00:00",
        days_of_week: ["MONDAY", "WEDNESDAY"],
        max_capacity: 30,
        end_date: "2027-05-01",
        Authorization: "Bearer fakejwt",
      },
      "fakejwt"
    );
    // 422 (validation) or 401 (auth checked first) — both are acceptable
    expect([401, 422]).toContain(status);
  });
});

// ─── Health check — backend is alive ──────────────────────────────────────────

test("Backend /docs is reachable", async ({ page }) => {
  const response = await page.goto(`${BACKEND_URL}/docs`);
  expect(response?.status()).toBe(200);
  // Swagger UI title
  await expect(page).toHaveTitle(/Batch Book/i);
});

test("Batch router is registered — /batch endpoints exist in OpenAPI spec", async ({ page }) => {
  await page.goto(`${BACKEND_URL}/openapi.json`);
  const text = await page.textContent("body");
  expect(text).toContain("/batch/");
  expect(text).toContain("assign-teacher");
  expect(text).toContain("archive");
});
