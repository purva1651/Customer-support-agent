.PHONY: lint test eval crm api frontend chat admin mcp

lint:
	ruff check .

test:
	pytest --basetemp=.pytest_tmp -m "not eval" --cov=app --cov-report=term --cov-fail-under=70

eval:
	pytest --basetemp=.pytest_tmp -m eval tests/evals/test_live_evals.py

crm:
	uvicorn mock_crm.main:app --host 0.0.0.0 --port 9000 --reload

api:
	uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload

frontend:
	cd frontend && npm run dev -- --host 0.0.0.0

chat: frontend

admin: frontend

mcp:
	python -m app.mcp_server.server
