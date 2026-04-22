# CBSE Analyzer

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
