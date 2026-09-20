def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _setup_client_and_order(client, token):
    client_id = client.post(
        "/api/clients",
        json={"client_name": "Script Test Client", "email": "scripttest@example.com"},
        headers=_headers(token),
    ).json()["id"]
    order_id = client.post(
        "/api/orders",
        json={"client_id": client_id, "package_name": "Basic", "contracted_video_count": 5},
        headers=_headers(token),
    ).json()["id"]
    return client_id, order_id


def test_script_status_transition_enforced(client, admin_token):
    token, _ = admin_token
    client_id, order_id = _setup_client_and_order(client, token)

    script_resp = client.post(
        "/api/scripts",
        json={"client_id": client_id, "order_id": order_id, "video_number": 1},
        headers=_headers(token),
    )
    assert script_resp.status_code == 201
    script = script_resp.json()
    assert script["status"] == "draft"

    # Illegal jump: draft -> approved should be rejected.
    bad_resp = client.put(
        f"/api/scripts/{script['id']}", json={"status": "approved"}, headers=_headers(token)
    )
    assert bad_resp.status_code == 400

    # Legal transition: draft -> assigned.
    ok_resp = client.put(
        f"/api/scripts/{script['id']}", json={"status": "assigned"}, headers=_headers(token)
    )
    assert ok_resp.status_code == 200
    assert ok_resp.json()["status"] == "assigned"
