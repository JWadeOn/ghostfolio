# Development Guide

Two ways to run the stack for development:

1. **Recommended: Run everything locally except Postgres and Redis** — Only Postgres and Redis run in Docker. The Ghostfolio API, Ghostfolio client, and the trading agent run on your host. You get hot reload (HMR) for the client and fast iteration on the API and agent without rebuilding images.
2. **Alternative: Run everything in Docker** — Single `docker compose up`, but code changes require rebuilding the Ghostfolio image (and optionally configuring Docker WATCH / HMR if you want automatic updates).

---

## Option 1: Run client, server, and trading agent locally (recommended)

Only **Postgres** and **Redis** run in Docker. The **Ghostfolio API**, **Ghostfolio client**, and **trading agent** run on your host so you get:

- Hot module replacement (HMR) for the Angular client
- No image rebuilds for frontend, API, or agent changes
- Trading Assistant in the UI at https://localhost:4200

### 1. Start only Postgres and Redis

From the `ghostfolio-trading-agent` directory:

```bash
docker compose up -d postgres redis
```

Leave these two containers running. Do **not** start the Ghostfolio or trading-agent containers so that ports 3333 and 8000 stay free for your local processes.

### 2. Configure the monorepo for local Postgres/Redis

From the **monorepo root** (parent of `ghostfolio-trading-agent`), ensure `.env` exists and matches the containers. The trading-agent Redis runs **without a password**; the Ghostfolio API must not send AUTH:

```env
# Postgres (same as docker-compose)
POSTGRES_DB=ghostfolio-db
POSTGRES_HOST=localhost
POSTGRES_USER=user
POSTGRES_PASSWORD=password
DATABASE_URL=postgresql://user:password@localhost:5432/ghostfolio-db?connect_timeout=300&sslmode=prefer

# Redis (no password — leave REDIS_PASSWORD empty)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# Required for Ghostfolio
ACCESS_TOKEN_SALT=super-secret-salt
JWT_SECRET_KEY=super-secret-jwt-key

# So the API proxies chat to your local agent
TRADING_AGENT_URL=http://localhost:8000
```

Use the same values as in `ghostfolio-trading-agent/docker-compose.yml`. **`REDIS_PASSWORD=` must be empty** or the API will get Redis auth errors.

### 3. Configure the trading agent for local Ghostfolio

In **`ghostfolio-trading-agent/.env`** set the agent to talk to your local API:

```env
GHOSTFOLIO_API_URL=http://localhost:3333
GHOSTFOLIO_ACCESS_TOKEN=<your-ghostfolio-token>
ANTHROPIC_API_KEY=<your-anthropic-api-key>
```

(See the main [README](README.md#1-configure-environment-variables) for how to get the Ghostfolio access token.)

### 4. Database schema and seed

From the monorepo root:

```bash
npm run database:push
npm run database:seed
```

### 5. Start the trading agent

From the **`ghostfolio-trading-agent`** directory (with your venv active if you use one):

```bash
pip install -r requirements.txt   # if not already installed
uvicorn agent.app:app --host 0.0.0.0 --port 8000
```

Leave it running. The agent serves at **http://localhost:8000**.

### 6. Start the Ghostfolio API

In a **second terminal**, from the monorepo root:

```bash
npm run start:server
```

Leave it running. The API serves at **http://localhost:3333** and proxies chat to the agent at http://localhost:8000.

### 7. Start the Ghostfolio client

In a **third terminal**, from the monorepo root:

```bash
npm run start:client
```

Open the URL the dev server prints (typically **https://localhost:4200** — accept the self-signed cert if prompted).

### 8. Use the Trading Assistant

- Sign in (e.g. with a security token from Ghostfolio **Settings → Account**).
- In the top nav, open **Trading Assistant** and use the chat.

**If the agent says "Ghostfolio is unreachable":** Confirm the API is up (`http://localhost:3333/api/v1/health`) and that the agent was started with `GHOSTFOLIO_API_URL=http://localhost:3333` in `ghostfolio-trading-agent/.env`.

---

## Option 2: Run everything in Docker

From the `ghostfolio-trading-agent` directory:

```bash
docker compose up --build
```

This builds Ghostfolio from source and starts Postgres, Redis, Ghostfolio, and the trading agent. Open **http://localhost:3333** for the app and **http://localhost:8000/docs** for the agent API.

### Code changes and automatic updates

The Ghostfolio **image** is built at `docker compose up --build` time. The client and API are compiled into that image, so:

- **Frontend or API code changes do not appear automatically.** You must **rebuild the image and restart** the Ghostfolio container to see changes:
  ```bash
  docker compose up -d --build ghostfolio
  ```

If you want **WATCH / HMR** so changes update automatically inside Docker, you would need to:

- Use a custom setup (e.g. a different Dockerfile or compose override) that mounts the monorepo source and runs the dev servers (`npm run start:server` and `npm run start:client`) inside a container, with volume mounts so file changes on your host are visible in the container. The default compose does **not** do this; it uses a production-style build.

For the fastest feedback loop on Ghostfolio UI, API, and agent changes, use **Option 1** (client, server, and agent locally).
