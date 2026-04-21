import io

from server import app


def test_home_page_loads():
    client = app.test_client()
    response = client.get("/")

    assert response.status_code == 200
    assert b"CBSE Analyzer Atelier" in response.data


def test_sample_analysis_renders_results():
    client = app.test_client()
    response = client.post("/", data={"action": "sample"})

    assert response.status_code == 200
    assert b"sample_gazette.txt" in response.data
    assert b"Student ledger" in response.data
    assert b"Download workbook" in response.data


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
