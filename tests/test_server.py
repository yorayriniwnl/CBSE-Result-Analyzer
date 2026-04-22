import base64
import types
from io import BytesIO

import pandas as pd

import app as app_module
from app import app
from server import app as server_app


def test_home_page_loads():
    client = app.test_client()
    response = client.get("/")

    assert response.status_code == 200
    assert b"CBSE Analyzer Atelier" in response.data
    assert app_module.PUBLIC_VERCEL_URL.encode("utf-8") in response.data
    assert b"Open Live Demo" in response.data
    assert app_module.PUBLIC_GITHUB_URL.encode("utf-8") in response.data
    assert b"View on GitHub" in response.data


def test_prefixed_home_page_loads():
    client = app.test_client()
    response = client.get("/cbse-result-analyzer")

    assert response.status_code == 200
    assert b"CBSE Analyzer Atelier" in response.data


def test_server_entrypoint_exposes_same_flask_app():
    assert server_app is app


def test_default_context_exposes_github_link():
    page = app_module._default_context()

    assert page["vercel_url"] == app_module.PUBLIC_VERCEL_URL
    assert page["vercel_label"] == app_module.PUBLIC_VERCEL_LABEL
    assert page["github_url"] == app_module.PUBLIC_GITHUB_URL
    assert page["github_label"] == app_module.PUBLIC_GITHUB_LABEL
    assert page["home_url"] == "/"
    assert page["download_url"] == "/download"


def test_default_context_uses_custom_domain_base_path():
    with app.test_request_context("/", base_url="https://yorayriniwnl.in"):
        page = app_module._default_context()

    assert page["home_url"] == "/cbse-result-analyzer"
    assert page["download_url"] == "/cbse-result-analyzer/download"


def test_forwarded_prefix_header_overrides_host_mapping():
    with app.test_request_context(
        "/",
        base_url="https://cbse-result-analyzer.vercel.app",
        headers={"X-Forwarded-Prefix": "/proxy-prefix"},
    ):
        page = app_module._default_context()

    assert page["home_url"] == "/proxy-prefix"
    assert page["download_url"] == "/proxy-prefix/download"


def test_run_dev_entrypoint_uses_flask(monkeypatch):
    calls = {"flask": 0}

    def fake_run(**kwargs):
        calls["flask"] += 1
        assert kwargs == {"debug": True}

    monkeypatch.setattr(app_module, "_running_inside_streamlit", lambda: False)
    monkeypatch.setattr(app_module, "_can_use_dev_reloader", lambda: True)
    monkeypatch.setattr(app_module, "_should_use_dev_reloader", lambda: True)
    monkeypatch.setattr(app_module, "_configured_dev_reloader_type", lambda: None)
    monkeypatch.setattr(app_module.app, "run", fake_run)

    app_module._run_dev_entrypoint()

    assert calls["flask"] == 1


def test_run_dev_entrypoint_passes_configured_reloader_type(monkeypatch):
    calls = {"flask": 0}

    def fake_run(**kwargs):
        calls["flask"] += 1
        assert kwargs == {"debug": True, "reloader_type": "stat"}

    monkeypatch.setattr(app_module, "_running_inside_streamlit", lambda: False)
    monkeypatch.setattr(app_module, "_can_use_dev_reloader", lambda: True)
    monkeypatch.setattr(app_module, "_should_use_dev_reloader", lambda: True)
    monkeypatch.setattr(app_module, "_configured_dev_reloader_type", lambda: "stat")
    monkeypatch.setattr(app_module.app, "run", fake_run)

    app_module._run_dev_entrypoint()

    assert calls["flask"] == 1


def test_run_dev_entrypoint_disables_reloader_off_main_thread(monkeypatch):
    calls = {"flask": 0}

    def fake_run(**kwargs):
        calls["flask"] += 1
        assert kwargs == {"debug": True, "use_reloader": False}

    monkeypatch.setattr(app_module, "_running_inside_streamlit", lambda: False)
    monkeypatch.setattr(app_module, "_can_use_dev_reloader", lambda: False)
    monkeypatch.setattr(app_module.app, "run", fake_run)

    app_module._run_dev_entrypoint()

    assert calls["flask"] == 1


def test_run_dev_entrypoint_disables_reloader_when_env_prefers_it(monkeypatch):
    calls = {"flask": 0}

    def fake_run(**kwargs):
        calls["flask"] += 1
        assert kwargs == {"debug": True, "use_reloader": False}

    monkeypatch.setattr(app_module, "_running_inside_streamlit", lambda: False)
    monkeypatch.setattr(app_module, "_can_use_dev_reloader", lambda: True)
    monkeypatch.setattr(app_module, "_should_use_dev_reloader", lambda: False)
    monkeypatch.setattr(app_module.app, "run", fake_run)

    app_module._run_dev_entrypoint()

    assert calls["flask"] == 1


def test_run_dev_entrypoint_shows_notice_inside_streamlit(monkeypatch):
    calls = {"notice": 0, "flask": 0}

    monkeypatch.setattr(app_module, "_running_inside_streamlit", lambda: True)

    def fake_notice():
        calls["notice"] += 1

    def fake_run(**kwargs):
        calls["flask"] += 1

    monkeypatch.setattr(app_module, "_render_streamlit_entrypoint_notice", fake_notice)
    monkeypatch.setattr(app_module.app, "run", fake_run)

    app_module._run_dev_entrypoint()

    assert calls["notice"] == 1
    assert calls["flask"] == 0


def test_should_use_dev_reloader_defaults_off_on_windows(monkeypatch):
    monkeypatch.delenv("FLASK_DEV_USE_RELOADER", raising=False)
    monkeypatch.setattr(app_module.os, "name", "nt", raising=False)

    assert app_module._should_use_dev_reloader() is False


def test_should_use_dev_reloader_can_be_enabled_via_env(monkeypatch):
    monkeypatch.setenv("FLASK_DEV_USE_RELOADER", "1")
    monkeypatch.setattr(app_module.os, "name", "nt", raising=False)

    assert app_module._should_use_dev_reloader() is True


def test_should_use_dev_reloader_can_be_disabled_via_env(monkeypatch):
    monkeypatch.setenv("FLASK_DEV_USE_RELOADER", "0")
    monkeypatch.setattr(app_module.os, "name", "posix", raising=False)

    assert app_module._should_use_dev_reloader() is False


def test_configured_dev_reloader_type_respects_env_override(monkeypatch):
    monkeypatch.setenv("FLASK_DEV_RELOADER_TYPE", "watchdog")

    assert app_module._configured_dev_reloader_type() == "watchdog"


def test_configured_dev_reloader_type_ignores_invalid_override(monkeypatch):
    monkeypatch.setenv("FLASK_DEV_RELOADER_TYPE", "banana")

    assert app_module._configured_dev_reloader_type() is None


def test_streamlit_detection_uses_runtime_context(monkeypatch):
    fake_runtime = types.ModuleType("streamlit.runtime")
    fake_scriptrunner = types.ModuleType("streamlit.runtime.scriptrunner")
    fake_scriptrunner.get_script_run_ctx = lambda: object()

    monkeypatch.setitem(app_module.sys.modules, "streamlit", types.ModuleType("streamlit"))
    monkeypatch.setitem(app_module.sys.modules, "streamlit.runtime", fake_runtime)
    monkeypatch.setitem(
        app_module.sys.modules,
        "streamlit.runtime.scriptrunner",
        fake_scriptrunner,
    )

    assert app_module._running_inside_streamlit() is True


def test_healthz_reports_runtime_resources():
    client = app.test_client()
    response = client.get("/healthz")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["resource_report"]["settings_exists"] is True
    assert payload["resource_report"]["subjects_exists"] is True
    assert payload["resource_report"]["templates_exists"] is True


def test_favicon_route_returns_no_content():
    client = app.test_client()
    response = client.get("/favicon.ico")

    assert response.status_code == 204
    assert response.data == b""


def test_prefixed_favicon_route_returns_no_content():
    client = app.test_client()
    response = client.get("/cbse-result-analyzer/favicon.ico")

    assert response.status_code == 204
    assert response.data == b""


def test_sample_analysis_renders_results():
    client = app.test_client()
    response = client.post("/", data={"action": "sample"})

    assert response.status_code == 200
    assert b"sample_gazette.txt" in response.data
    assert b"Student ledger" in response.data
    assert b"Download workbook" in response.data


def test_prefixed_sample_analysis_renders_results():
    client = app.test_client()
    response = client.post("/cbse-result-analyzer", data={"action": "sample"})

    assert response.status_code == 200
    assert b"sample_gazette.txt" in response.data
    assert b"Download workbook" in response.data


def test_custom_domain_home_uses_prefixed_form_action():
    client = app.test_client()
    response = client.get("/", base_url="https://yorayriniwnl.in")

    assert response.status_code == 200
    assert b'action="/cbse-result-analyzer"' in response.data


def test_custom_domain_download_action_is_prefixed():
    client = app.test_client()
    response = client.post(
        "/",
        data={"action": "sample"},
        base_url="https://yorayriniwnl.in",
    )

    assert response.status_code == 200
    assert b'action="/cbse-result-analyzer/download"' in response.data


def test_sample_mode_missing_resource_shows_error(monkeypatch):
    client = app.test_client()

    def raise_missing_sample():
        raise FileNotFoundError("sample_gazette.txt")

    monkeypatch.setattr(app_module, "_sample_text", raise_missing_sample)
    response = client.post("/", data={"action": "sample"})

    assert response.status_code == 200
    assert b"bundled sample gazette file is unavailable" in response.data.lower()


def test_download_route_returns_workbook():
    client = app.test_client()
    analyze_response = client.post("/", data={"action": "sample"})
    assert analyze_response.status_code == 200

    raw_payload_marker = b'name="raw_payload" hidden>'
    marker_index = analyze_response.data.find(raw_payload_marker)
    assert marker_index != -1

    payload_start = marker_index + len(raw_payload_marker)
    payload_end = analyze_response.data.find(b"</textarea>", payload_start)
    raw_payload = analyze_response.data[payload_start:payload_end].decode("utf-8")

    response = client.post(
        "/download",
        data={
            "raw_payload": raw_payload,
            "school_name": "CBSE Results 2026",
            "output_name": "sample_analysis.xlsx",
        },
    )

    assert response.status_code == 200
    assert response.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert response.headers["Content-Disposition"].endswith('filename=sample_analysis.xlsx')


def test_prefixed_download_route_returns_workbook():
    client = app.test_client()
    analyze_response = client.post("/cbse-result-analyzer", data={"action": "sample"})
    assert analyze_response.status_code == 200

    raw_payload_marker = b'name="raw_payload" hidden>'
    marker_index = analyze_response.data.find(raw_payload_marker)
    assert marker_index != -1

    payload_start = marker_index + len(raw_payload_marker)
    payload_end = analyze_response.data.find(b"</textarea>", payload_start)
    raw_payload = analyze_response.data[payload_start:payload_end].decode("utf-8")

    response = client.post(
        "/cbse-result-analyzer/download",
        data={
            "raw_payload": raw_payload,
            "school_name": "CBSE Results 2026",
            "output_name": "sample_analysis.xlsx",
        },
    )

    assert response.status_code == 200
    assert response.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_download_route_rejects_invalid_payload():
    client = app.test_client()
    response = client.post("/download", data={"raw_payload": "not-base64"})

    assert response.status_code == 400
    assert b"Invalid workbook payload." in response.data


def test_payload_encoding_round_trips_and_uses_compression():
    raw_text = "SCHOOL : - 123 TEST SCHOOL\n" * 20

    payload = app_module._encode_payload(raw_text)

    assert payload.startswith(app_module.PAYLOAD_ENCODING_PREFIX)
    assert app_module._decode_payload(payload) == raw_text


def test_download_route_accepts_legacy_base64_payload():
    client = app.test_client()
    raw_text = app_module._sample_text()
    legacy_payload = base64.b64encode(raw_text.encode("utf-8")).decode("ascii")

    response = client.post(
        "/download",
        data={
            "raw_payload": legacy_payload,
            "school_name": "CBSE Results 2026",
            "output_name": "legacy_payload.xlsx",
        },
    )

    assert response.status_code == 200
    assert response.headers["Content-Disposition"].endswith(
        "filename=legacy_payload.xlsx"
    )


def test_large_upload_returns_friendly_error(monkeypatch):
    client = app.test_client()
    original_limit = app.config["MAX_CONTENT_LENGTH"]
    monkeypatch.setitem(app.config, "MAX_CONTENT_LENGTH", 64)

    response = client.post(
        "/",
        data={
            "gazette_file": (BytesIO(b"A" * 256), "large.txt"),
            "school_name": "CBSE Results 2026",
            "output_name": "large.xlsx",
        },
        content_type="multipart/form-data",
    )

    monkeypatch.setitem(app.config, "MAX_CONTENT_LENGTH", original_limit)

    assert response.status_code == 413
    assert b"Upload a CBSE gazette under" in response.data


def test_analysis_rejects_payloads_that_are_too_large_for_roundtrip(monkeypatch):
    client = app.test_client()
    monkeypatch.setattr(app_module, "MAX_ROUNDTRIP_PAYLOAD_BYTES", 8)

    response = client.post("/", data={"action": "sample"})

    assert response.status_code == 200
    assert b"too large to safely round-trip" in response.data


def test_prepare_toppers_prefers_passing_students():
    student_df = pd.DataFrame(
        [
            {
                "Roll No": "2",
                "Name": "Fail Kid",
                "Gender": "M",
                "Total Marks": 550,
                "Percentage": 99,
                "Subjects Appeared": 6,
                "Result": "FAIL",
            },
            {
                "Roll No": "1",
                "Name": "Pass Kid",
                "Gender": "F",
                "Total Marks": 500,
                "Percentage": 95,
                "Subjects Appeared": 6,
                "Result": "PASS",
            },
        ]
    )

    toppers = app_module._prepare_toppers(student_df)

    assert toppers[0]["name"] == "Pass Kid"
    assert all(topper["result_label"] == "PASS" for topper in toppers)
