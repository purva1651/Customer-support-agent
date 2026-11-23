.PHONY: lint test crm api chat admin

lint:
	ruff check .

test:
	pytest

crm:
	uvicorn mock_crm.main:app --host 0.0.0.0 --port 9000 --reload

api:
	uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload

chat:
	chainlit run frontend/chat_app.py

admin:
	streamlit run frontend/admin_app.py
