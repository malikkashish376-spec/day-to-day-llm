.PHONY: install seed run test eval eval-holdout demo clean docker

export PYTHONPATH := src

install:
	pip install -r requirements.txt

seed:
	python -m daytoday.cli seed

run:
	uvicorn daytoday.api:app --reload --port 8000

test:
	python -m pytest

eval:
	python eval/run_eval.py --baseline && python eval/run_eval.py

eval-holdout:
	python eval/run_eval.py --baseline --dataset heldout.jsonl --tag heldout

demo: seed test
	@echo "Demo data loaded, tests green. Now run: make run"

docker:
	docker compose up --build

clean:
	rm -rf data/*.db data/*.db-wal data/*.db-shm .pytest_cache
	find . -name __pycache__ -type d -exec rm -rf {} +
