# WireGUI

A self-hosted WireGuard VPN management platform built with Python, NiceGUI, and PostgreSQL.

WireGUI gives you a clean web interface for managing WireGuard peers, firewall rules, and user authentication -- without depending on any third-party cloud service. It's designed for teams and individuals who want full control over their VPN infrastructure.

## Against enshittification

This project exists because we believe infrastructure software should serve its users, not its investors. Too many open-source VPN tools have been enshittified -- features locked behind paid tiers, telemetry quietly added, self-hosting made deliberately painful to push you toward a managed offering.

WireGUI is AGPL-licensed specifically to prevent this. If you run it, you own it. If you modify it and offer it as a service, you share the source. No bait-and-switch, no open-core grift, no "community edition" that mysteriously lacks the features you actually need.

Software that manages your network traffic should be fully transparent and fully yours.

## Features

- **WireGuard management** -- create/delete peers, automatic IP allocation (IPv4 + IPv6), QR codes and `.conf` downloads
- **Firewall rules** -- per-user nftables chains with CIDR, protocol, and port range support
- **Multi-factor auth** -- TOTP authenticator apps and WebAuthn security keys
- **SSO** -- OpenID Connect and SAML identity providers with auto-provisioning
- **Magic links** -- passwordless email login
- **API tokens** -- programmatic access via REST API (`/api/v0`)
- **Dark/light theme** -- user preference stored in profile, auto mode follows system
- **VPN session management** -- configurable session duration with automatic peer expiry
- **Real-time stats** -- live RX/TX counters and handshake tracking
- **Diagnostics** -- WAN connectivity checks, peer status, system notifications

## Tech stack

| Layer | Technology |
|-------|-----------|
| UI | NiceGUI (reactive server-side, WebSocket) |
| API | FastAPI (built into NiceGUI) |
| ORM | SQLModel (SQLAlchemy + Pydantic) |
| Database | PostgreSQL (asyncpg) |
| Cache | Valkey (Redis-compatible) |
| Migrations | Alembic |
| Auth | authlib, python-jose, pyotp, webauthn, bcrypt |
| VPN | WireGuard (`wg` + `ip` CLI) |
| Firewall | nftables (`nft` CLI) |
| Python | 3.13+ |

## Quick start

```bash
# Clone and install
git clone https://forge.provvedo.com/provvedo/wiregui.git
cd wiregui
uv sync

# Start PostgreSQL and Valkey
docker compose up -d

# Run migrations and start
alembic upgrade head
uv run python -m wiregui.main
```

Open http://localhost:13000 -- an admin account is created automatically on first run (check the logs for the generated password).

## Production deployment

```bash
# Docker Compose (recommended)
docker compose -f compose.prod.yml up -d
```

The container runs migrations on startup, manages the WireGuard interface, and requires `NET_ADMIN` + `SYS_MODULE` capabilities. See `compose.prod.yml` for the full configuration including environment variables.

### Environment variables

All settings use the `WG_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `WG_DATABASE_URL` | `postgresql+asyncpg://wiregui:wiregui@localhost/wiregui` | PostgreSQL connection |
| `WG_REDIS_URL` | `redis://localhost:6379/0` | Valkey/Redis connection |
| `WG_SECRET_KEY` | `change-me-in-production` | JWT signing + Fernet encryption key |
| `WG_WG_ENABLED` | `false` | Enable WireGuard interface management |
| `WG_WG_ENDPOINT_HOST` | `localhost` | Public endpoint for client configs |
| `WG_WG_ENDPOINT_PORT` | `51820` | WireGuard listen port |
| `WG_WG_IPV4_NETWORK` | `10.3.2.0/24` | IPv4 tunnel network |
| `WG_WG_IPV6_NETWORK` | `fd00::3:2:0/120` | IPv6 tunnel network |
| `WG_ADMIN_EMAIL` | `admin@localhost` | Initial admin email |
| `WG_ADMIN_PASSWORD` | *(auto-generated)* | Initial admin password |
| `WG_EXTERNAL_URL` | `http://localhost:13000` | Public-facing URL |
| `WG_IDP_CONFIG_FILE` | *(none)* | Path to YAML file with OIDC/SAML IdP definitions |

## Testing

```bash
# Unit + integration tests
uv run pytest

# E2E tests (Playwright — requires running PostgreSQL, Valkey, and mock-oidc)
docker compose up -d
uv run pytest tests/e2e/ -v

# E2E in headed mode (watch tests in a browser)
uv run pytest tests/e2e/ --headed --slowmo 300
```

E2E tests automatically start a WireGUI instance on port 13001 and use Playwright's async API to drive a real Chromium browser. The `--headed` flag opens a visible browser window and `--slowmo` adds a delay (in ms) between actions for debugging. The OIDC login flow tests use the `mock-oidc` service from `compose.yml`.

### IdP provisioning from YAML

Identity providers can be seeded at startup from a YAML file, enabling GitOps and infrastructure-as-code workflows:

```bash
WG_IDP_CONFIG_FILE=/etc/wiregui/idps.yaml uv run python -m wiregui.main
```

See `tests/e2e/test_idp_seed.py` for the YAML format and seeding behavior.

## License

Copyright 2026 Stefano Bertelli / Provvedo

This program is free software: you can redistribute it and/or modify it under the terms of the **GNU Affero General Public License** as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This means: if you run a modified version of WireGUI as a network service, you must make the source code available to users of that service. No exceptions, no loopholes.

See [LICENSE](LICENSE) for the full text.
