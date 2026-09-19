.PHONY: install test workflow db-up db-down

install:
	pip install -r requirements.txt

test:
	pytest -v

workflow:
	python tests/test_workflow.py

db-up:
	docker compose up -d

db-down:
	docker compose down -v
