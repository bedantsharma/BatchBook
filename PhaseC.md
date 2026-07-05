## PHASE C — Production Deployment 🟡 PARTIAL (C.5 pending)

**Decision to make first:** Where to host the backend?

| Option | Cost | Pros | Cons |
|--------|------|------|------|
| **Render.com** | Free (spins down) / $7/mo (always-on) | Dead simple Docker deploy, no ops | Free tier sleeps after 15 min inactivity |
| **Railway.app** | ~$5/mo | Good DX, fast deploys | Less mature |
| **Fly.io** | ~$3–5/mo | Fastest cold starts | CLI-heavy setup |
| **DigitalOcean Droplet** | $6/mo | Full control, persistent | You manage the server |

**Recommendation:** Start with **Render.com** (the $7/month "Starter" plan — no sleep). The database is already on Supabase so no DB cost. Frontend goes on **Vercel** (already set up in B.2). Total cost: ~$7/month.

---

### Task C.1 — Buy a domain ✅ DONE

- [x] Buy a `.com` or `.in` domain — suggestions: `batchbook.in`, `batchbook.app`, `trybatchbook.com`
- [x] Recommended registrar: Namecheap or Google Domains
- [x] Note the domain here once purchased: **Domain: batchbook.in (Namecheap)**

---

### Task C.2 — Set up Render.com for the backend ✅ DONE

- [x] Sign up at render.com
- [x] "New Web Service" → connect `github.com/bedantsharma/BatchBook`
- [x] Environment: Docker
- [x] Dockerfile path: `./Dockerfile`
- [x] Docker build target: `prod`
- [x] Set all env vars in Render dashboard:
  - `DATABASE_URL`
  - `SUPABASE_URL`
  - `SUPABASE_KEY`
  - `RAZORPAY_KEY_ID`
  - `RAZORPAY_KEY_SECRET`
  - `PROJECT_NAME=BatchBook`
  - `PORT=8000`
- [x] First deploy: service is live on the default `*.onrender.com` URL
- [x] Verify `https://batchbook-g9c0.onrender.com/docs` loads — confirmed, Swagger UI renders ("Batch Book - Swagger UI")
- [x] Migrations — same Supabase DB as dev, already at head; no manual `alembic upgrade head` needed
- [x] Custom domain `api.batchbook.in` added in Render, DNS CNAME added in Namecheap, domain verified (had to clear Namecheap's default parking CNAME/URL-redirect records and a conflicting CAA record first — Let's Encrypt cert issuance needs a clean CAA or one that allows `letsencrypt.org`)

**Verified by:** _(bedant sharma — live at api.batchbook.in, /docs confirmed loading)_

---

### Task C.3 — Configure frontend for production ✅ DONE

- [x] Add custom domain in Vercel: `batchbook.in` (naked domain) + `www.batchbook.in`
- [x] Update CORS in `app.py` — added `https://batchbookui.vercel.app`, `https://batchbook.in`, `https://www.batchbook.in` to `allow_origins` (done before first Render deploy, to avoid a redeploy just for CORS)
- [x] In Vercel project settings, add env var: `VITE_API_BASE_URL=https://api.batchbook.in`
- [x] Fixed a bug along the way: `batchbookui/.env.production` (committed to git) had a leftover placeholder `VITE_API_BASE_URL=https://your-backend-url.com`, and the Vercel dashboard var had initially been misnamed `VITE_API_URL` — neither matched what `src/services/api.js` actually reads (`VITE_API_BASE_URL`), so OTP requests were silently calling the wrong host. Fixed in both places (PR [#25](https://github.com/bedantsharma/batchbookui/pull/25), merged) and redeployed.

**Verified by:** _(bedant sharma — confirmed OTP requests hit api.batchbook.in after the fix)_

---

### Task C.4 — Set up CI/CD with GitHub Actions ✅ DONE

**Why:** Without CI, a bad push goes straight to prod. With CI, tests run first and the deploy only happens if tests pass.

- [x] Created `.github/workflows/deploy-backend.yml` — a `test` job (`uv run pytest -q`) runs on every push *and* every PR into `master`; a `deploy` job runs only on a direct push to `master`, only after `test` passes, and curls the Render deploy hook
- [x] `RENDER_DEPLOY_HOOK` GitHub secret added (from Render dashboard → service → Settings → Deploy Hook)
- [x] For frontend: Vercel already auto-deploys on every push to `batchbookui` — no extra config needed

**Verified by:** _(bedant sharma — pushed to master 2026-06-23, confirmed via `gh run watch`: `test` passed in 22s, `deploy` job fired the Render hook successfully — run [28049802701](https://github.com/bedantsharma/BatchBook/actions/runs/28049802701))_

---

### Task C.5 — Smoke test the full production stack

- [ ] Owner flow end-to-end on `https://yourdomain.com` (phone login → setup → batches → fees → attendance)
- [ ] Student flow: parent OTP → student dashboard → see real data
- [ ] Open browser DevTools → Network tab → confirm zero 404s on API calls
- [ ] Test on a real phone (not just desktop Chrome) — these users are on Android phones

**Verified by:** _(pending)_

---