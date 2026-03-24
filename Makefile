.PHONY: dev backend frontend install

# One-command dev startup
dev:
	@echo "Starting CoReviewer..."
	@make backend &
	@make frontend

backend:
	PYTHONPATH=. uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev

install:
	pip install -r backend/requirements.txt
	cd frontend && npm install
