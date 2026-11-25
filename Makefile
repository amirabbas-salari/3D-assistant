.PHONY: dev build start agent web api check clean

dev:
	npm run dev

build:
	npm run build

start:
	npm run start

agent:
	python -m sam.agent start

web:
	npm run dev --workspace=@3d-assistant/web

api:
	node apps/api/src/index.js

check:
	python scripts/check_env.py
	python scripts/check_voice_flow.py

clean:
	rm -rf dist apps/web/dist .rag node_modules/.cache
