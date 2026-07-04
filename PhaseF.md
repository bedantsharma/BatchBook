## PHASE F — Multi-Tenant Payment Settlement (Bring-Your-Own Razorpay Account) 🟡 IN PROGRESS (F.1–F.4 built, F.5–F.7 remaining)

**Why this phase exists:** `clients/razorpay_client.py` builds one global `razorpay.Client` from your personal `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`, and `fee_service.py: generate_payment_link()` uses that same client for every institute's fee records. **Every parent payment, for every owner, currently settles into your own Razorpay account, not the owner's.** Fine for a single pilot institute (yours); breaks the moment a second real owner signs up — you'd be holding other people's tuition money and manually forwarding it, which is an operational headache and a real regulatory question under RBI's Payment Aggregator (PA-PG) rules.

There is also no webhook handler today — `PATCH /fee/record/{id}/pay` requires an owner to manually mark a record paid after checking Razorpay's dashboard themselves. Nothing confirms a payment server-side.

### Decision: each owner brings their own Razorpay account (decided 2026-06-23, supersedes the 2026-06-21 Route decision)

Route + Linked Accounts (the original plan) was abandoned after two findings: (1) a Razorpay support-chatbot claim about a ₹40L turnover eligibility threshold turned out to be unverifiable and likely a conflation with an unrelated GST rule; (2) reading Razorpay's actual Linked Accounts docs showed there is **no hosted KYC redirect** for Route — BatchBook itself would have had to collect each owner's bank details, contradicting the entire premise of "BatchBook never touches sensitive data." On top of that, RBI's Sept 15, 2025 Master Direction on Payment Aggregators states a PA business "shall not carry out marketplace business" and requires marketplaces to ensure sellers are separately, fully onboarded — tightening exactly the kind of money-aggregation Route relies on.

**Chosen model:** owner signs up for their own Razorpay merchant account directly at razorpay.com (Individual or Proprietorship business type — Udyam registration is the realistic business-proof document for a solo coaching institute), completes KYC independently, and pastes their own API Key ID/Secret into a new BatchBook Settings page. BatchBook never custodies or routes anyone else's money — each institute's payments go straight to that institute's own Razorpay account. This was the option rejected in the original comparison table for onboarding friction; it's back because it's the only model where BatchBook doesn't aggregate funds across unrelated merchants, keeping it outside PA-PG scope (the same pattern used by SaaS platforms that let a customer "bring their own payment gateway").

Open questions from the decision doc are now resolved:
- **Platform fee model:** flat subscription instead of a per-transaction cut (Route's auto-split is gone since money never touches a BatchBook-controlled account) — ₹700/month up to 50 students, ₹15/student above that headcount.
- **Website requirement:** confirmed via Razorpay's own FAQ — no website is required to generate live API keys or use Payment Links.
- **PA-PG scope:** confirmed by analogy to an existing BYO-keys model the user has direct experience with at their day job — same pattern, same conclusion (outside PA-PG scope).
- **Onboarding UX:** KYC is fully offloaded to Razorpay's own (reportedly painless) onboarding flow; BatchBook's job is just a guided Settings page explaining what the owner is about to do, not replicating any part of KYC itself.

### Step-by-step: how this fits into the existing flow

1. **Signup/setup is unchanged.** Owner still does OTP → `/owner/setup` (institute name + city only — `OwnerSetup.jsx` → `POST /owner/institute`) → lands at `/owner/dashboard`, exactly as today.
2. **A new Settings page is added to the dashboard** (doesn't exist yet — `OwnerDashboard.jsx`'s sidebar currently only has Students / Batches / Fees / Attendance / Tests). It has a "Payouts" section: a guided explainer ("you'll need your own Razorpay account to collect fees online — here's what that involves") plus two input fields for Key ID and Key Secret, and a connection status (`Not connected` / `Connected` / `Needs reconnect`).
3. **The trigger is lazy, not forced.** The first time an owner clicks "Generate Payment Link" on a fee record without connected keys, a banner appears — "Connect your Razorpay account to start collecting fees online" — linking to Settings → Payouts. Cash-only institutes never see this at all.
4. **Owner signs up at razorpay.com independently**, completes their own KYC (Individual/Proprietorship + Udyam), and generates a Key ID + Secret from their own Dashboard → Account & Settings → API Keys.
5. **Owner pastes Key ID + Secret into BatchBook's Settings page.** Backend validates the key prefix (`rzp_live_`, reject/warn on `rzp_test_`), runs a cheap test call (e.g. fetch account details) to confirm the keys actually work, then encrypts the secret at rest and stores both on the `Institute` row. Status becomes `Connected`.
6. **Every `generate_payment_link()` call for that institute** instantiates a `razorpay.Client(key_id, key_secret)` scoped to that institute instead of the global client — no `transfers` array, no split logic, because the money was never BatchBook's to route in the first place.
7. **Parent pays the link** → money lands directly in the owner's own Razorpay account → settles to their own bank account on their own account's normal cycle. BatchBook never holds or moves the money at any point.
8. **If the owner rotates/revokes keys on their own dashboard**, the next payment-link call fails with an auth error. BatchBook catches this, flips status to `Needs reconnect`, and shows a clear reconnect prompt in Settings rather than failing silently.

---

### Task F.1 — Add Razorpay credential fields to `Institute` and a Settings page ✅ DONE

- [x] Add nullable `razorpay_key_id` (plain), `razorpay_key_secret_encrypted` (**encrypted at rest**), and a `razorpay_status` enum (`NOT_CONNECTED` / `CONNECTED` / `NEEDS_RECONNECT`) to `InstituteSchema` — migrated with Alembic
- [x] Added `Settings → Payouts` to the dashboard sidebar and a corresponding route
- [x] Built the "Payouts" section: guided explainer of what connecting Razorpay involves, Key ID/Secret input fields, connection status badge
- [x] On the Fees page, a "Connect Payouts" banner shows the first time an owner without connected keys tries to generate a payment link

**PR:** [#42](https://github.com/bedantsharma/BatchBook/pull/42) (backend) + [#36](https://github.com/bedantsharma/batchbookui/pull/36) (frontend)

**Verified by:** _(bedant sharma — merged and live)_

---

### Task F.2 — Validate and store owner-provided keys ✅ DONE (pending PR merge)

- [x] Encrypt `razorpay_key_secret` at rest (Fernet, key from `RAZORPAY_ENCRYPTION_KEY`); Settings `GET` returns only a `secret_configured: bool` indicator, never the secret itself
- [x] Missing `RAZORPAY_ENCRYPTION_KEY` now returns a clear `503`, not a generic `500` — fixed after initial deploy ([#43](https://github.com/bedantsharma/BatchBook/pull/43))
- [x] On Settings save: reject keys that don't start with `rzp_live_` (covers `rzp_test_` and anything else) with a `400` explaining test-mode payments won't settle anywhere real — `InstituteService.connect_razorpay()` in `services/institute_service.py`
- [x] Run a lightweight Razorpay API call (`client.payment.all({"count": 1})`, via `asyncio.to_thread`) with the submitted keys before saving, to confirm they authenticate; `razorpay.errors.BadRequestError` → `InvalidRazorpayCredentialsError` → `400` in `routes/owner_route.py`'s `update_razorpay_payouts`. Previously any syntactically-plausible key was accepted and only failed at the first real payment-link generation attempt

**PR:** [#42](https://github.com/bedantsharma/BatchBook/pull/42), [#43](https://github.com/bedantsharma/BatchBook/pull/43), key-prefix/liveness validation (this branch, not yet a PR)

**Verified by:** _(bedant sharma — encryption + masking merged and live; key-prefix/liveness validation code-complete 2026-07-03, 323/323 backend tests passing, pending PR + manual smoke test with a real test-mode key)_

---

### Task F.3 — Per-institute Razorpay client in `fee_service.py` ✅ DONE (pending PR #46 merge)

- [x] Added `build_institute_razorpay_client(institute)` in `clients/razorpay_client.py` — builds a client from the institute's own decrypted credentials, returns `None` if not connected (never raises for the "not connected" case, so callers can branch cleanly)
- [x] `GET /fee/record/{record_id}/payment-link` now uses the institute's own client instead of the platform's global one — returns `503` if not connected. **Behavior change:** previously this endpoint silently used the platform's shared account for every institute regardless of whether they'd connected their own
- [x] The old global `get_razorpay_client()` is now unused by any payment-link code path (left in place rather than deleted, in case of future platform-side billing use — see Task F.6)
- [ ] Split/transfer logic was never built (the Route model was abandoned before implementation — see the Phase F decision note above), so there was nothing to remove here

**PR:** [#46](https://github.com/bedantsharma/BatchBook/pull/46) (open, not yet merged)

**Verified by:** _(pending PR #46 merge + deploy; 320/320 backend tests passing on the branch)_

---

### Task F.3b — Payment success callback page + backfill for missing payment links ✅ DONE (pending PR #46 merge)

**Why:** Two gaps closed alongside F.3: parents had no confirmation screen after paying (Razorpay's redirect went nowhere), and fee records created before an owner connects Razorpay would never get a payment link unless someone manually revisited every one.

- [x] Razorpay payment links now set `callback_url` to `{FRONTEND_BASE_URL}/payment-success` and `callback_method: "get"`
- [x] New `/payment-success` page (`batchbookui`) reads Razorpay's `razorpay_payment_link_status` query param — shows a real confirmation only when it equals `paid`, a neutral "not completed" message otherwise. No webhook exists (see Task F.4), so this page cannot confirm payment server-side — it's a landing page, not a source of truth
- [x] `FeeService.backfill_missing_payment_links(db, institute_id, month)` — finds last month's fee records missing a link, generates one per record for institutes with Razorpay connected, skips/reports institutes that aren't, tolerates per-record failures without aborting the batch
- [x] `POST /admin/backfill-payment-links` — manual trigger, protected by an `X-Admin-Secret` header (`ADMIN_BACKFILL_SECRET` env var)
- [x] Daily in-process APScheduler job runs the same sweep automatically, guarded by a Postgres advisory lock so it can't double-fire across Render's 2 prod uvicorn workers
- [ ] Set `FRONTEND_BASE_URL`, `ADMIN_BACKFILL_SECRET`, `ENABLE_SCHEDULER` in Render's env vars at next deploy
- [ ] Manual smoke test: hit the admin endpoint against a real Razorpay test-mode institute, confirm a link appears on an unpaid record

**PR:** [#46](https://github.com/bedantsharma/BatchBook/pull/46) (backend, open) + [#37](https://github.com/bedantsharma/batchbookui/pull/37)/[#38](https://github.com/bedantsharma/batchbookui/pull/38) (frontend, merged)

**Verified by:** _(pending — backend PR #46 not yet merged; Render env vars and live admin-endpoint smoke test still to do)_

---

### Task F.4 — Per-institute Razorpay payment webhook handling ✅ DONE (pending PR + smoke test)

**Why:** Payment confirmation is currently 100% manual. A webhook makes the fee status update itself the moment Razorpay confirms payment, and unblocks the auto fee-receipt WhatsApp send already planned in Task D.2. Each owner's Razorpay account has its own webhook secret, so the single global `RAZORPAY_WEBHOOK_SECRET` assumption from the old Route plan no longer holds.

- [x] Added nullable `razorpay_webhook_secret_encrypted` column to `InstituteSchema` (migration `a24386059615`); `PATCH /owner/institute/payouts/webhook` saves the secret the owner pastes in after registering BatchBook's webhook URL in their own Razorpay dashboard — `InstituteService.set_webhook_secret()`. `RazorpayPayoutResponse` now also returns `webhook_configured`
- [x] Added `POST /webhooks/razorpay/{institute_id}` in `routes/webhook_route.py` (no JWT auth — verified by signature instead), keyed per institute so the right stored secret is used for verification
- [x] Verifies the `X-Razorpay-Signature` header against the raw request body using `razorpay.Utility().verify_webhook_signature()` and that institute's decrypted stored secret; invalid/missing signature → `400`, no webhook configured for that institute → `404`
- [x] Handles the `payment_link.paid` event: looks up the `FeeRecord` by its stored `payment_link` (short_url) via `FeeRepository.get_record_by_payment_link()`, adds the webhook's `amount_paid` (paise) to the record's existing `amount_paid`, then calls `fee_service.mark_payment()` with Razorpay's `payment.id` as the reference. Already-`FULLY_PAID` records short-circuit as a no-op so a retried webhook delivery can't double-count. Unrecognized events and unmatched payment links are acknowledged (`200`) but ignored so Razorpay doesn't retry forever
- [x] Refactored the fee-receipt WhatsApp send (previously inlined in the manual `PATCH /fee/record/{id}/pay` route) into `FeeService.notify_fee_receipt_if_fully_paid()`, shared by both the manual endpoint and the new webhook — this is what actually "unblocks" the auto-receipt-on-real-payment flow the Why note above refers to
- [x] `PATCH /fee/record/{id}/pay` is unchanged for manual/offline (cash) payments — still works exactly as before
- [x] 26 new/updated tests (webhook signature/event handling, idempotency, partial + full payment amounts, institute/fee service unit tests) — 349/349 backend tests passing

**Not built:** no frontend UI yet for the owner to see/paste the webhook secret in Settings → Payouts (F.1's Payouts page only has Key ID/Secret fields today) — needed before an owner can actually turn this on

**Verified by:** _(code-complete 2026-07-03, not yet a PR; no manual smoke test against a real Razorpay test-mode webhook yet)_

---

### Task F.5 — Key rotation/revocation detection

- [ ] On any `generate_payment_link()` auth failure against an institute's stored keys, flip `Institute` payout status to `Needs reconnect` and surface that state clearly in Settings
- [ ] Add a manual "Test connection" button in Settings that re-validates the stored keys on demand (reuses the Task F.2 validation call)

**Verified by:** _(pending)_

---

### Task F.6 — Subscription billing for the platform fee

**Why:** Route's automatic 97/3 split is gone — BatchBook needs its own billing mechanism now that it never touches owner payment flows. Pricing decided: ₹700/month up to 50 students, ₹15/student above that headcount.

- [ ] Decide and implement how BatchBook charges institutes for its own subscription (separate Razorpay subscription/invoice on BatchBook's own account, billed to the owner directly — not a transaction split)
- [ ] Track per-institute student headcount to compute the tier/overage at billing time

**Verified by:** _(pending)_

---

### Task F.7 — End-to-end test before onboarding a second real owner

- [ ] In Razorpay test mode (on a real Razorpay test account, not BatchBook's): paste test keys into Settings, generate a payment link, pay it with a test card/UPI, confirm the webhook fires and `FeeRecord` updates automatically
- [ ] Confirm the reconnect flow: revoke the test keys on the Razorpay dashboard, confirm the next payment-link call flips status to `Needs reconnect`, reconnect with fresh keys, confirm it recovers
- [ ] Only after this passes: onboard the first real second owner

**Verified by:** _(pending)_

---