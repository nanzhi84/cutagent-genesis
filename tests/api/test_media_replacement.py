import hashlib

from fastapi.testclient import TestClient

from apps.api.main import app, repository
from tests.fixtures.media import generate_test_video

client = TestClient(app)


def login_admin() -> None:
    response = client.post("/api/auth/login", json={"email": "admin@local.cutagent", "password": "local-admin"})
    assert response.status_code == 200, response.text


def upload_video(tmp_path, *, filename: str, case_id: str, title: str | None = None, replace_mode: bool = False) -> dict:
    video = generate_test_video(tmp_path, duration_sec=1, width=160, height=120, fps=15, filename=filename)
    content = video.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    prepared = client.post(
        "/api/uploads/prepare",
        json={
            "kind": "broll",
            "case_id": case_id,
            "filename": filename,
            "content_type": "video/mp4",
            "size_bytes": len(content),
            "sha256": digest,
        },
    )
    assert prepared.status_code == 201, prepared.text
    upload = prepared.json()
    uploaded = client.put(f"/api/uploads/{upload['id']}/file", files={"file": (filename, content, "video/mp4")})
    assert uploaded.status_code == 200, uploaded.text
    metadata = {"title": title or filename}
    if replace_mode:
        metadata["template_mode"] = "replace"
    completed = client.post(
        "/api/uploads/complete",
        json={"upload_session_id": upload["id"], "size_bytes": len(content), "sha256": digest, "metadata": metadata},
    )
    assert completed.status_code == 200, completed.text
    return completed.json()


def test_single_replace_source_preserves_existing_annotation(tmp_path):
    login_admin()
    original = upload_video(tmp_path, filename="single-original.mp4", case_id="case_single_replace")
    asset_id = original["media_asset"]["id"]
    editor = client.get(f"/api/annotations/{asset_id}").json()
    patched = client.patch(
        f"/api/annotations/{asset_id}",
        json={
            "etag": editor["etag"],
            "patch": {"operations": [{"op": "replace", "path": "/canonical/segments", "value": [{"label": "keep"}]}]},
        },
    )
    assert patched.status_code == 200, patched.text
    replacement = upload_video(
        tmp_path, filename="single-replacement.mp4", case_id="case_single_replace", replace_mode=True
    )
    assert replacement["media_asset"] is None

    response = client.post(
        f"/api/media/assets/{asset_id}/replace-source",
        json={"upload_session_id": replacement["upload_session"]["id"]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["asset"]["id"] == asset_id
    assert body["artifact"]["artifact_id"] == replacement["artifact"]["artifact_id"]
    assert body["preserved_annotation"] is True
    assert repository().annotations[asset_id].canonical["segments"] == [{"label": "keep"}]


def test_auto_match_replace_reports_matched_unmatched_and_ambiguous(tmp_path):
    login_admin()
    matched = upload_video(tmp_path, filename="Hero Clip.mp4", case_id="case_auto_replace", title="Hero Clip")
    upload_video(tmp_path, filename="Duplicate A.mp4", case_id="case_auto_replace", title="Duplicate")
    upload_video(tmp_path, filename="Duplicate B.mp4", case_id="case_auto_replace", title="Duplicate")
    matched_asset_id = matched["media_asset"]["id"]
    replacement = upload_video(tmp_path, filename="hero-clip.mp4", case_id="case_auto_replace", replace_mode=True)
    unmatched = upload_video(tmp_path, filename="missing.mp4", case_id="case_auto_replace", replace_mode=True)
    ambiguous = upload_video(tmp_path, filename="duplicate.mp4", case_id="case_auto_replace", replace_mode=True)

    response = client.post(
        "/api/media/assets/auto-match-replace",
        json={
            "case_id": "case_auto_replace",
            "kind": "broll",
            "upload_session_ids": [
                replacement["upload_session"]["id"],
                unmatched["upload_session"]["id"],
                ambiguous["upload_session"]["id"],
            ],
        },
    )

    assert response.status_code == 200, response.text
    results = {item["filename"]: item for item in response.json()["results"]}
    assert results["hero-clip.mp4"]["status"] == "matched"
    assert results["hero-clip.mp4"]["asset_id"] == matched_asset_id
    assert results["missing.mp4"]["status"] == "unmatched"
    assert results["duplicate.mp4"]["status"] == "ambiguous"
    assert repository().media_assets[matched_asset_id].source_artifact_id == replacement["artifact"]["artifact_id"]
