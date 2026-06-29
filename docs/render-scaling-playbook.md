# Render Scaling Playbook

This guide covers when and how to scale BatchBook's backend on Render.com as user load increases.

## When to Scale: Active User Milestones

Scaling is driven by concurrent user count (active students/teachers at any moment), not total accounts. Monitor via Render's Metrics tab (CPU, memory, request latency).

### Milestone 1: 500 Active Users → Render Standard Plan

**Symptoms:**
- CPU consistently >70% on Render Starter
- Request latency approaching 200ms under load
- Database connection pool saturation warnings in logs

**Action:** Upgrade from **Starter** ($7/month, 1 vCPU) to **Standard** ($25/month, 2 vCPU) in Render Dashboard.
- Render redeploys the same build to the new plan with zero code changes.
- Update `Dockerfile` prod CMD from `--workers 2` to `--workers 4` (formula: 2 × vCPU + 1 minus 1 for uvicorn overhead, or just double it).

### Milestone 2: 2,000 Active Users → Add 2nd Instance for Load Balancing

**Symptoms:**
- Single Standard instance cannot reliably handle peak load
- Spiky traffic during class times causes request queuing
- Want zero-downtime deploys without dropping requests

**Action:** Deploy a second Render service (separate from the first):
1. In Render Dashboard, create a **new Web Service** pointing to the same BatchBook repo and Dockerfile.
2. Set identical environment variables (`DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_KEY`, `RAZORPAY_KEY_ID`, etc.).
3. Both instances attach to the **same PostgreSQL database** (all write conflicts are handled by Postgres's ACID transactions).
4. Point the frontend and API clients to a **DNS round-robin** or **reverse proxy** (e.g., CloudFlare, Nginx):
   - Round-robin: Add both Render instance URLs to A/CNAME records pointing to your domain.
   - Reverse proxy: Set up a single entry point that distributes traffic to both backends.
5. Zero-downtime deploys: Deploy to one instance while the other absorbs traffic, then switch.

**Database connectivity:** Both instances see the same `DATABASE_URL`. There is no per-instance state — auth is stateless JWT, and batch processing is handled via database locks, not in-memory queues.

### Milestone 3: 5,000+ Active Users → Render Pro + Supabase Supavisor

**Symptoms:**
- Connection limit warnings even with 2 Standard instances (each uses `pool_size=20`, so 40 total connections can approach PostgreSQL's 100-connection default).
- Want deterministic scaling without worry about prepared statement cache conflicts.

**Action:**
1. Upgrade both Render instances to **Pro** ($85/month, 4 vCPU each) for more CPU/memory headroom.
2. **Switch DATABASE_URL to Supabase's Supavisor transaction-mode pooler** (explained below).

## Supabase Supavisor Switch

Supavisor is a built-in connection pooler on Supabase that sits between your app and PostgreSQL. Transaction mode allows short-lived connections and automatic cleanup.

### When to Switch
- You are approaching database connection limits across multiple instances.
- You want to guarantee prepared statement cache isolation (avoids "prepared statement already exists" errors under load).

### How to Switch

**Step 1:** In Supabase Dashboard → Project Settings → Database → Connection strings, locate the **Supavisor** row (labeled "Pooler", port 6543).

Copy the full connection string. It looks like:
```
postgresql://[user]:[password]@[project].pooler.supabase.co:6543/postgres
```

**Step 2:** In Render Dashboard → BatchBook service → Environment → set `DATABASE_URL` to this Supavisor connection string.

**Step 3:** No code changes needed. The app already has this comment in `db/session.py`:
```python
# When switching DATABASE_URL to Supabase's Supavisor transaction-mode pooler
# (port 6543), also add: connect_args={"statement_cache_size": 0}
# to avoid "prepared statement already exists" errors under load.
```

If you switch and encounter "prepared statement already exists" errors:
- Stop the affected instance and manually apply the fix to `db/session.py`:
  ```python
  _engine_kwargs = {
      "echo": get_settings().db_echo,
      "connect_args": {"statement_cache_size": 0},  # ← Add this line
  }
  ```
- Redeploy both instances.

**Performance trade-off:** Supavisor adds ~5–10ms latency per query due to connection pooling overhead, but solves connection exhaustion. At 5k+ concurrent users, this trade-off is worthwhile.

## Stateless Architecture (Why Multiple Instances Work)

BatchBook is **fully stateless** and safe to run on multiple instances:

- **Authentication:** All auth is stateless JWT (issued by Supabase). No session storage, no per-instance login state.
- **Database:** PostgreSQL is the single source of truth. Every instance queries the same DB. No in-memory caches of user data or batch state.
- **Background jobs:** None yet. When Phase 4 (attendance alerts) and Phase 3 (fee reminders) are implemented, use a **separate Render service** or Supabase Edge Functions for scheduled tasks — do not run cron inside uvicorn workers.

**Implication:** You can safely add/remove instances at any time. Requests can be routed to any instance without loss of user context.

## Checklist for Scaling Actions

**At 500 active users:**
- [ ] Monitor Render Metrics for 1 week to confirm traffic pattern
- [ ] Upgrade Render plan to Standard
- [ ] Update Dockerfile: change `--workers 2` to `--workers 4`
- [ ] Redeploy
- [ ] Verify latency drops below 150ms under load

**At 2,000 active users:**
- [ ] Create a second Render service (same repo, same env vars)
- [ ] Set up DNS load balancing or reverse proxy
- [ ] Deploy both instances
- [ ] Test zero-downtime deploy: deploy to instance A while instance B takes traffic, switch

**At 5,000+ active users:**
- [ ] Upgrade both Render instances to Pro ($85 each)
- [ ] Switch DATABASE_URL to Supabase Supavisor (port 6543)
- [ ] Redeploy both instances
- [ ] Monitor logs for "prepared statement" errors; if seen, apply `connect_args` fix

## Monitoring & Alerts

Set up Render Alerts in Dashboard for:
- CPU > 80% for 5+ minutes
- Memory > 90%
- Requests/sec > {your threshold}
- Error rate > 1%

Also monitor Supabase logs for slow queries or connection errors.

## Rollback

If you scale up and encounter issues:
1. Switch back to the previous plan (Starter → Standard), or remove the 2nd instance.
2. Revert DATABASE_URL from Supavisor back to the direct port 5432 string.
3. Redeploy.

No data is lost — all changes are to infrastructure, not data.
