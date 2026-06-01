/**
 * E2E tests for Attendance (Task 4.1 + 4.3)
 *
 * These tests drive the full stack via Playwright.
 * Prerequisites: `make dev-d` must be running.
 *
 * Tests verify:
 * - Attendance endpoints exist and return correct HTTP codes
 * - Auth is required for protected endpoints
 * - Payload validation works (422 on bad input)
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

// ─── Backend reachability ─────────────────────────────────────────────────────

test("backend /docs is reachable", async () => {
  const res = await fetch(`${BACKEND_URL}/docs`);
  expect(res.status).toBe(200);
});

// ─── Auth guard tests ─────────────────────────────────────────────────────────

test("POST /attendance/session returns 422 without required fields (no auth header)", async () => {
  const { status } = await apiPost("/attendance/session", {});
  // Missing required fields → 422 (Pydantic validation), or 401 if auth checked first
  expect([401, 422]).toContain(status);
});

test("GET /attendance/session/1 returns 401 without token", async () => {
  const { status } = await apiGet("/attendance/session/1");
  expect(status).toBe(401);
});

test("GET /attendance/batch/1 returns 401 without token", async () => {
  const { status } = await apiGet("/attendance/batch/1");
  expect(status).toBe(401);
});

test("GET /attendance/student/1 returns 422 or 401 without token or month param", async () => {
  const { status } = await apiGet("/attendance/student/1");
  // Missing month query param → 422, or 401 if auth checked first
  expect([401, 422]).toContain(status);
});

test("POST /attendance/session/1/mark returns 401 without token", async () => {
  const { status } = await apiPost("/attendance/session/1/mark", {
    present_enrollment_ids: [],
  });
  expect(status).toBe(401);
});

// ─── Payload validation ───────────────────────────────────────────────────────

test("POST /attendance/session with invalid token returns 401", async () => {
  const { status } = await apiPost(
    "/attendance/session",
    {
      batch_id: 1,
      date: "2026-05-30",
      start_time: "16:00:00",
      end_time: "17:00:00",
    },
    "Bearer invalid_token_xyz"
  );
  expect(status).toBe(401);
});

test("POST /attendance/session/1/mark with invalid token returns 401", async () => {
  const { status } = await apiPost(
    "/attendance/session/1/mark",
    { present_enrollment_ids: [1, 2, 3] },
    "Bearer invalid_token_xyz"
  );
  expect(status).toBe(401);
});

// ─── OpenAPI schema verification ──────────────────────────────────────────────

test("attendance routes are registered in OpenAPI schema", async () => {
  const res = await fetch(`${BACKEND_URL}/openapi.json`);
  expect(res.status).toBe(200);
  const schema = await res.json();
  const paths = Object.keys(schema.paths ?? {});
  expect(paths).toContain("/attendance/session");
  expect(paths).toContain("/attendance/session/{session_id}");
  expect(paths).toContain("/attendance/session/{session_id}/mark");
  expect(paths).toContain("/attendance/batch/{batch_id}");
  expect(paths).toContain("/attendance/student/{enrollment_id}");
});
