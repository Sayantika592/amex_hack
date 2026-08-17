.PHONY: demo install init taxonomy data validate rahul eval test build-frontend clean fetch-models verify-models clean-models clean-models-force

install:
	pip install -r backend/requirements.txt
	cd frontend && npm install --no-audit --no-fund

init:
	python -m backend.db.init

taxonomy:
	python -m validation.validate_taxonomy

data:
	python -m data.generate --count 10000 --seed 42

validate:
	python -m data.validate

rahul:
	python -m evaluation.run_rahul

eval:
	python -m evaluation.run_evaluation

fetch-models:
	python scripts/fetch_models.py

verify-models:
	python scripts/fetch_models.py --verify-only

clean-models:
	python scripts/clean_models.py

clean-models-force:
	python scripts/clean_models.py --yes

test:
	python -m pytest backend/tests/ -q

build-frontend:
	cd frontend && npm run build

demo:
	bash scripts/start_demo.sh

clean:
	rm -rf var/dispute.db frontend/dist
