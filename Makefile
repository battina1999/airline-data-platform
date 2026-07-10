# ==================================================================
# Airline Data Platform - developer entrypoints
# Run `make help` to see everything.
#
# Data source (synthetic | bts):
#   make pipeline                 # synthetic demo data
#   make pipeline SOURCE=bts      # real US DOT BTS data (see docs/data_profile.md)
# ==================================================================
.DEFAULT_GOAL := help
SHELL := /bin/bash

DBT_DIR := dbt/airline_dwh
SOURCE ?= synthetic
export DATA_SOURCE := $(SOURCE)

.PHONY: help setup generate ingest quality dbt-deps dbt-build reconcile pipeline dashboard test clean docker-up docker-down

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Install python dependencies
	pip install -r requirements.txt

generate: ## Generate synthetic raw source data (flights, airports, carriers, weather)
	python -m data.generate_data

ingest: ## Extract + load raw files into the warehouse (Talend-style ETL)
	python -m ingestion.run_ingestion

quality: ## Run Great Expectations validation on the raw layer
	python -m quality.validate

dbt-deps: ## Install dbt packages
	cd $(DBT_DIR) && dbt deps

dbt-build: ## Build + test all dbt models (staging -> dims/facts -> marts)
	cd $(DBT_DIR) && dbt build --profiles-dir .

reconcile: ## Source-to-target row-count reconciliation
	python -m quality.reconciliation

pipeline: ## Run the entire pipeline end-to-end (SOURCE=synthetic|bts)
	python -m orchestration.run_pipeline
	@echo "Pipeline complete. Launch the dashboard with: make dashboard"

profile-data: ## Profile the BTS files -> docs/data_profile.md
	python scripts/profile_data.py

dashboard: ## Launch the Streamlit analytics dashboard
	streamlit run dashboards/streamlit_app.py

test: ## Run python unit tests
	python -m pytest -q

clean: ## Remove generated data + warehouse + dbt artifacts
	rm -rf warehouse data/raw/*.csv $(DBT_DIR)/target $(DBT_DIR)/dbt_packages $(DBT_DIR)/logs

docker-up: ## Start Airflow + Postgres + dashboard via Docker
	docker compose up -d

docker-down: ## Stop all containers
	docker compose down
