## PHASE B — Real Landing Page  ✅Done

**Why this comes before deployment:** Two reasons:
1. WATI (WhatsApp Business API) requires a business website URL during Meta verification. The current placeholder card at `/` doesn't count — Meta looks for a real page with product description, privacy policy, and contact info.
2. When an owner hears about BatchBook (word of mouth, Google search), they need to land somewhere that convinces them to sign up.

---

### Task B.1 — Build a real marketing landing page

**Replace** `src/components/LandingPage.jsx` with a proper page. It does not need to be fancy — it needs to communicate clearly.

Required sections:

- [x] **Hero:** headline + "Get Started Free" CTA → `/onboarding`
- [x] **3 feature cards:** Fee Management, Attendance, Test Scores
- [x] **How it works:** 3 numbered steps + second CTA
- [x] **Social proof placeholder:** "Join 50+ coaching institutes"
- [x] **Footer:** BatchBook © 2026 · Privacy Policy link · contact email
- [x] **Privacy Policy page** at `/privacy-policy` — covers data collection, usage, retention, contact
- [x] **Add `/privacy-policy` route in `App.jsx`**
- [x] **Fix Vercel SPA routing** — `vercel.json` rewrite rule so direct URL hits don't 404

**Verified by:** _(deployed at batchbookui.vercel.app — pending visual check)_

---

### Task B.2 — Deploy landing page to get a real URL

**Why:** Before the full Docker deployment, get `yourdomain.com` serving the landing page so you can submit the URL to WATI immediately.

Recommended approach: **Vercel** (free, instant, auto-deploys from git push, gives HTTPS)

- [x] Push `batchbookui` frontend to its own GitHub repo
- [x] Sign up at vercel.com → import `batchbookui` repo → set env vars → deployed
- [x] Vercel URL: **https://batchbookui.vercel.app** — submit this to WATI as business URL
- [ ] Later (Task C.3), point your custom domain here and update the WATI registration

**Verified by:** _(live at batchbookui.vercel.app — /privacy-policy confirmed working after vercel.json fix)_

---