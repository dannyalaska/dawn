.PHONY: check test dev-api dev-ui
check:
	poetry run ruff check .
	poetry run ruff format .
	poetry run black --check .
	poetry run mypy .
	poetry run pytest

test:
	poetry run pytest

dev-api:
	poetry run uvicorn app.api.server:app --reload --port 8000

dev-ui:
	poetry run streamlit run app/streamlit_app/main.py
