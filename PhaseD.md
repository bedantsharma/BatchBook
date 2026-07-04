## PHASE D — WhatsApp Notifications via Meta Cloud API 🟢 READY (verification approved 2026-06-21)

> Going direct to Meta's Cloud API instead of WATI — see "Decision" note in Current Reality above. No BSP, no monthly fee, same integration shape originally planned for WATI.

---

### Task D.0 — One-time Meta-side setup (do first, no code)

- [x] In Meta Business Suite → Business Settings → System Users: create/use a System User, generate a **permanent access token** (scopes `whatsapp_business_messaging`, `whatsapp_business_management`, expiry: Never) — the default testing-page token expires in ~1-2h and will break prod notifications silently if used by mistake
- [x] In WhatsApp Manager: note the `phone_number_id` and `WABA ID` for the verified number
- [x] Confirm current messaging tier (new WABAs start at 250 unique recipients/24h) — fine at current scale, just be aware before any bulk "remind-all" send

---

### Task D.1 — WhatsApp client + notification service

- [x] Add to `.env`: `META_WHATSAPP_TOKEN=xxxxxxxx`, `META_WHATSAPP_PHONE_NUMBER_ID=xxxxxxxx`
- [x] Add to `config.py` Settings class: `meta_whatsapp_token: str` and `meta_whatsapp_phone_number_id: str` (replaces the unused `wati_api_endpoint` / `wati_api_token` fields)
- [x] Create `BatchBook/clients/whatsapp_client.py` — async HTTP client using `httpx`; one method `send_template_message(phone, template_name, params, language="en")` that POSTs to `https://graph.facebook.com/v23.0/{phone_number_id}/messages`
- [x] Update `BatchBook/services/notification_service.py` — replace the WATI-stub log lines with real calls into `whatsapp_client`; keep the same four function signatures (`send_enrollment_invite`, `send_fee_reminder`, `send_fee_receipt`, `send_absence_alert`)

---

### Task D.2 — Fee reminder and receipt (Tasks 3.4)

**Templates to create in WhatsApp Manager** (category: Utility → wait for approval, usually minutes–24h):
- `fee_reminder`: "Hi {{1}}, your fee of ₹{{2}} for {{3}} is due on {{4}}." + URL button → Razorpay payment link (pass the link as the button's dynamic URL param, don't embed it in body text)
- `fee_receipt`: "Hi {{1}}, payment of ₹{{2}} received for {{3}} on {{4}}. Thank you!"

- [x] Add to `fee_route.py`: `POST /fee/remind/{record_id}` and `POST /fee/remind-all`
- [x] Auto-send `fee_receipt` template after `mark_payment()` succeeds in `fee_service.py`
- [x] Wire the "Remind" button in `FeesPage.jsx` to call `POST /fee/remind/{record_id}` (batchbookui PR #26)

---

### Task D.3 — Absence alert (Task 4.2)

**Template to create in WhatsApp Manager** (category: Utility):
- `absence_alert`: "Hi, {{1}} was absent from {{2}} today ({{3}}). Please contact us if this is unexpected."

- [x] Add `send_absence_alert(enrollment_id, date)` to `notification_service.py`
- [x] In `attendance_service.py` `bulk_mark()`: after writing ABSENT rows, fire `send_absence_alert` as a background task (use FastAPI `BackgroundTasks`) for each newly-absent enrollment
- [x] Don't block the HTTP response on the WhatsApp call — use `BackgroundTasks` so the attendance mark is instant

---