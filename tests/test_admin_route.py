"""Integration tests for POST /admin/seed-demo-accounts."""


async def test_seed_demo_accounts_requires_admin_secret(client):
    response = await client.post("/admin/seed-demo-accounts")
    assert response.status_code == 401


async def test_seed_demo_accounts_rejects_wrong_secret(client):
    response = await client.post(
        "/admin/seed-demo-accounts", headers={"X-Admin-Secret": "wrong"}
    )
    assert response.status_code == 401


async def test_seed_demo_accounts_creates_data(client):
    response = await client.post(
        "/admin/seed-demo-accounts", headers={"X-Admin-Secret": "test-admin-secret"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["owner_created"] is True
    assert body["institute_created"] is True
    assert sorted(body["batches_created"]) == ["Class 10 Maths", "Class 12 Physics"]
    assert body["student_created"] is True
    assert body["sessions_created"] == 6
    assert body["fee_records_created"] == 4


async def test_seed_demo_accounts_is_idempotent_via_http(client):
    first = await client.post(
        "/admin/seed-demo-accounts", headers={"X-Admin-Secret": "test-admin-secret"}
    )
    assert first.status_code == 200

    second = await client.post(
        "/admin/seed-demo-accounts", headers={"X-Admin-Secret": "test-admin-secret"}
    )
    assert second.status_code == 200
    body = second.json()
    assert body["owner_created"] is False
    assert body["institute_created"] is False
    assert body["batches_created"] == []
    assert body["student_created"] is False
    assert body["sessions_created"] == 0
    assert body["fee_records_created"] == 0
