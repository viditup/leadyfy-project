def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _create_client(client, token):
    resp = client.post(
        "/api/clients",
        json={"client_name": "Order Test Client", "email": "ordertest@example.com"},
        headers=_headers(token),
    )
    return resp.json()["id"]


def test_create_order_and_production_counter(client, admin_token):
    token, _ = admin_token
    client_id = _create_client(client, token)

    order_resp = client.post(
        "/api/orders",
        json={
            "client_id": client_id,
            "package_name": "Growth Package",
            "contracted_video_count": 10,
            "pricing": 40000,
            "gst_tax": 7200,
            "total_invoice_amount": 47200,
        },
        headers=_headers(token),
    )
    assert order_resp.status_code == 201
    order = order_resp.json()
    assert order["outstanding_balance"] == 47200

    counter_resp = client.get(
        f"/api/orders/{order['id']}/production-counter", headers=_headers(token)
    )
    assert counter_resp.status_code == 200
    counter = counter_resp.json()
    assert counter["ordered_videos"] == 10
    assert counter["delivered_videos"] == 0
    assert counter["remaining_quota"] == 10


def test_invalid_order_returns_404(client, admin_token):
    token, _ = admin_token
    response = client.get("/api/orders/not-a-real-id", headers=_headers(token))
    assert response.status_code == 404


def test_client_portal_can_list_own_orders_only(client, db_session, admin_token, portal_client_factory):
    """
    Regression test for the previously-missing GET /api/orders/portal/mine
    route (spec 2.D "View active orders, production progress").
    """
    token, _ = admin_token
    client_a, token_a = portal_client_factory("Order Portal Client A", "orderportal.a@example.com")
    client_b, _ = portal_client_factory("Order Portal Client B", "orderportal.b@example.com")

    resp_a = client.post(
        "/api/orders",
        json={"client_id": client_a.id, "package_name": "Starter Pack", "contracted_video_count": 8},
        headers=_headers(token),
    )
    assert resp_a.status_code == 201
    resp_b = client.post(
        "/api/orders",
        json={"client_id": client_b.id, "package_name": "Growth Pack", "contracted_video_count": 20},
        headers=_headers(token),
    )
    assert resp_b.status_code == 201

    portal_resp = client.get("/api/orders/portal/mine", headers=_headers(token_a))
    assert portal_resp.status_code == 200
    items = portal_resp.json()["items"]
    assert all(o["client_id"] == client_a.id for o in items)
    assert any(o["package_name"] == "Starter Pack" for o in items)
    assert not any(o["package_name"] == "Growth Pack" for o in items)


def test_client_portal_cannot_list_all_orders(client, portal_client_factory):
    """The internal-staff-only list must stay off-limits from the portal token."""
    _, token_a = portal_client_factory("Order Portal Client C", "orderportal.c@example.com")
    response = client.get("/api/orders", headers=_headers(token_a))
    assert response.status_code == 403
