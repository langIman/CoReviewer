.PHONY: dev backend frontend install

# One-command dev startup
dev:
	@echo "Starting CoReviewer..."
	@make backend &
	@make frontend

backend:
	@mkdir -p logs
	PYTHONPATH=. uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 2>&1 | tee logs/backend.log

frontend:
	@mkdir -p logs
	cd frontend && npm run dev 2>&1 | tee ../logs/frontend.log

install:
	pip install -r backend/requirements.txt
	cd frontend && npm install
