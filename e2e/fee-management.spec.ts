/**
 * E2E tests for Fee Management API (Task 3.5)
 *
 * Tests the fee management backend endpoints through the full stack.
 * Prerequisites: `make dev-d` must be running with a real Supabase-backed DB.
 * (These tests target the feature/fee-management-backend branch API once merged.)
 *
 * Pattern mirrors batch-management.spec.ts — unauthenticated access checks verify
 * the routes are registered and protected, without needing a live auth token.
 */

import { expect, test } from "@playwright/test";

const BACKEND_URL = "http://localhost:8000";

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

async function apiPatch(path: string, body: unknown, token = "") {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BACKEND_URL}${path}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify(body),
  });
  return { status: res.status, body: await res.json().catch(() => null) };
}

// ─── Unauthenticated access checks ────────────────────────────────────────────

test.describe("Fee API — unauthenticated access", () => {
  test("GET /fee/dashboard returns 401 or 422 without Authorization header", async () => {
    const { status } = await apiGet("/fee/dashboard?month=2026-05");
    expect([401, 422]).toContain(status);
  });

  test("POST /fee/structure returns 401 or 422 without Authorization header", async () => {
    const { status } = await apiPost("/fee/structure", {
      batch_id: 1,
      monthly_amount: 1500,
    });
    expect([401, 422]).toContain(status);
  });

  test("POST /fee/generate/1 returns 401 or 422 without Authorization header", async () => {
    const { status } = await apiPost("/fee/generate/1?month=2026-05", null);
    expect([401, 422]).toContain(status);
  });

  test("PATCH /fee/record/1/pay returns 401 or 422 without Authorization header", async () => {
    const { status } = await apiPatch("/fee/record/1/pay", {
      amount_paid: 1500,
      reference: "Cash",
    });
    expect([401, 422]).toContain(status);
  });

  test("GET /fee/batch/1 returns 401 or 422 without Authorization header", async () => {
    const { status } = await apiGet("/fee/batch/1?month=2026-05");
    expect([401, 422]).toContain(status);
  });

  test("GET /fee/structure/1 returns 401 or 422 without Authorization header", async () => {
    const { status } = await apiGet("/fee/structure/1");
    expect([401, 422]).toContain(status);
  });
});

// ─── Frontend fee management page ─────────────────────────────────────────────

test.describe("Fee Management UI", () => {
  test("navigating to /owner/dashboard and clicking Fees shows the fee management page", async ({
    page,
  }) => {
    // Navigate directly — in CI this requires the user to already be logged in
    // via session storage or the test to handle the OTP flow.
    // This smoke test just verifies the page renders at all when a valid session
    // is already present. Skip if no session (redirected to /phone-login).
    await page.goto("/owner/dashboard");

    const url = page.url();
    if (url.includes("phone-login")) {
      test.skip(true, "No active auth session — full flow requires OTP login");
      return;
    }

    // Click Fees in the sidebar
    await page.getByRole("button", { name: /fees/i }).first().click();

    // Wait for Fee Management heading
    await expect(page.getByText("Fee Management")).toBeVisible({ timeout: 5000 });
  });
});
