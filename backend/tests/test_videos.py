def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _setup_client_and_order(client, token):
    client_id = client.post(
        "/api/clients",
        json={"client_name": "Video Test Client", "email": "videotest@example.com"},
        headers=_headers(token),
    ).json()["id"]
    order_id = client.post(
        "/api/orders",
        json={"client_id": client_id, "package_name": "Basic", "contracted_video_count": 5},
        headers=_headers(token),
    ).json()["id"]
    return client_id, order_id


def test_video_pipeline_forward_transitions(client, admin_token):
    token, _ = admin_token
    client_id, order_id = _setup_client_and_order(client, token)

    video = client.post(
        "/api/videos", json={"client_id": client_id, "order_id": order_id}, headers=_headers(token)
    ).json()
    assert video["status"] == "script_approved"

    # Cannot skip straight to delivered.
    skip_resp = client.post(
        f"/api/videos/{video['id']}/transition", json={"status": "delivered"}, headers=_headers(token)
    )
    assert skip_resp.status_code == 400

    # Walk it forward one legal step at a time.
    for target in ["shoot_pending", "raw_footage_received", "video_editing", "internal_qa", "client_review"]:
        resp = client.post(
            f"/api/videos/{video['id']}/transition", json={"status": target}, headers=_headers(token)
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == target


def test_video_delivery_requires_link(client, admin_token):
    token, _ = admin_token
    client_id, order_id = _setup_client_and_order(client, token)
    video = client.post(
        "/api/videos", json={"client_id": client_id, "order_id": order_id}, headers=_headers(token)
    ).json()

    for target in [
        "shoot_pending",
        "raw_footage_received",
        "video_editing",
        "internal_qa",
        "client_review",
        "final_approved",
    ]:
        client.post(f"/api/videos/{video['id']}/transition", json={"status": target}, headers=_headers(token))

    resp = client.post(
        f"/api/videos/{video['id']}/transition", json={"status": "delivered"}, headers=_headers(token)
    )
    assert resp.status_code == 400
