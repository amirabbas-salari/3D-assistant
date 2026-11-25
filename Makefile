.PHONY: dev build start agent web api check clean docker-local docker-local-down

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

# لوکال کامل (LiveKit + API + Web + Agent)
docker-local:
	docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.local.yml up --build

docker-local-down:
	docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.local.yml down

# فقط LiveKit لوکال
livekit:
	docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.local.yml up livekit

check:
	python scripts/check_env.py
	python scripts/check_voice_flow.py

clean:
	rm -rf dist apps/web/dist .rag node_modules/.cache
