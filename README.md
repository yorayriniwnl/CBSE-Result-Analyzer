# YOR // CBSE Result Analyzer

> Evidence-led CBSE gazette analysis with parser notes and workbook export.

| Surface / claim | State | Boundary |
|---|---|---|
| Flask upload, parse, preview, and workbook download | VERIFIED | Covered by local tests and the server-rendered route. |
| Streamlit analysis studio | DEMO | Local studio surface; it is not the Vercel deployment entrypoint. |
| Gazette parser and Excel exporter | VERIFIED | Deterministic code path exercised by the test suite. |
| Bundled sample dataset | REPORTED | Included for a repeatable local walkthrough. |
| Optional hosted studio integrations | EXPERIMENTAL | Non-Flask integrations are not part of the verified deployment path. |
| Vercel deployment | UNVERIFIED | Deployment health and environment variables require a live check. |
| Broader production hardening | PLANNED | Operational limits, observability, and security review remain separate work. |

The interface follows the YOR visual contract: `#000000` void, `#050505` graphite,
`#e84b4b` crimson, `#671515` deep crimson, `#ff8a7f` signal, `#f5eaea` warm white,
`#c4c4c4` muted text, and the `#671515 → #8c1616 → #2a0505` field gradient.
Run `python scripts/check_design.py` to verify the contract across both UI surfaces.

This project ships with three entrypoints:

- `python app.py` starts the Flask app for local web runs and matches the Vercel deployment entrypoint.
- `python -m streamlit run streamlit_app.py` starts the Streamlit studio UI.
- `python main.py <gazette.txt> [output.xlsx] [--school "School Name"]` runs the CLI converter.

## Local setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Run locally

Flask app:

```bash
python app.py
```

Streamlit studio:

```bash
python -m streamlit run streamlit_app.py
```

CLI:

```bash
python main.py sample_gazette.txt
```

## Tests

```bash
python -m pytest
```
