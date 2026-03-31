# WireGUI

## Project Overview
WireGUI is a Python rewrite of the Wirezone VPN management platform (Elixir/Phoenix).
Original source: `/home/stefanob/PycharmProjects/personal/wirezone`

## Tech Stack
- **UI Framework**: NiceGUI (reactive server-side UI over WebSocket)
- **ORM/Models**: SQLModel (SQLAlchemy + Pydantic)
- **Database**: PostgreSQL (via asyncpg)
- **Cache/Sessions**: Valkey (Redis-compatible)
- **Migrations**: Alembic
- **REST API**: FastAPI (built into NiceGUI)
- **Auth**: authlib (OIDC), python-jose (JWT), pyotp (TOTP), webauthn, bcrypt
- **VPN**: subprocess calls to `wg` and `ip` commands
- **Firewall**: python-nftables or subprocess `nft`
- **Python**: 3.13
- **Package Manager**: uv

## Development Setup
```bash
uv sync                          # Install dependencies
docker compose up -d             # Start PostgreSQL and Valkey
alembic upgrade head             # Run migrations
uv run python -m wiregui.main    # Start the application
```

## Project Structure
```
wiregui/
├── main.py              # NiceGUI entrypoint, mounts FastAPI, starts background tasks
├── config.py            # pydantic-settings: Settings class
├── db.py                # async SQLAlchemy engine + sessionmaker
├── redis.py             # Valkey connection pool
├── models/              # SQLModel table definitions
│   ├── user.py
│   ├── device.py
│   ├── rule.py
│   ├── mfa_method.py
│   ├── oidc_connection.py
│   ├── api_token.py
│   ├── connectivity_check.py
│   └── configuration.py
├── schemas/             # Pydantic request/response schemas (non-table)
├── auth/                # Authentication modules
│   ├── passwords.py     # bcrypt hashing
│   ├── jwt.py           # JWT create/verify
│   ├── session.py       # NiceGUI session middleware
│   ├── oidc.py          # authlib OIDC
│   ├── saml.py          # python3-saml
│   ├── mfa.py           # TOTP + WebAuthn
│   └── api_token.py     # API token auth
├── api/v0/              # REST API routers
│   ├── users.py
│   ├── devices.py
│   ├── rules.py
│   └── configuration.py
├── pages/               # NiceGUI page definitions
│   ├── layout.py        # shared sidebar/header
│   ├── login.py
│   ├── devices.py       # user device CRUD
│   ├── account.py       # user account/MFA
│   ├── mfa_challenge.py
│   └── admin/           # admin pages
│       ├── users.py
│       ├── devices.py
│       ├── rules.py
│       ├── settings.py
│       └── diagnostics.py
├── services/            # Core services
│   ├── wireguard.py     # WG interface management
│   ├── firewall.py      # nftables rule management
│   ├── events.py        # DB → WG/firewall bridge
│   ├── notifications.py # in-memory notification queue
│   └── email.py         # aiosmtplib
├── tasks/               # Background tasks
│   ├── vpn_session.py   # expire VPN sessions
│   ├── stats.py         # poll WG stats
│   ├── connectivity.py  # WAN connectivity checks
│   └── oidc_refresh.py  # refresh OIDC tokens
└── utils/               # Utilities
    ├── crypto.py        # keypair gen, Fernet encrypt/decrypt
    ├── network.py       # IP allocation, CIDR validation
    └── validators.py    # shared validators
alembic/
├── env.py
├── script.py.mako
└── versions/
```

## Commands
- `uv sync` — install/update dependencies
- `uv run python -m wiregui.main` — run the app
- `alembic revision --autogenerate -m "description"` — create migration
- `alembic upgrade head` — apply all migrations
- `alembic downgrade -1` — rollback last migration
- `docker compose up -d` — start local Postgres + Valkey
- `docker compose down` — stop local services
- `pytest` — run tests

## Conventions
- Use SQLModel for all database models (combines SQLAlchemy table + Pydantic validation)
- Use async database sessions with asyncpg
- Place all NiceGUI pages in `wiregui/pages/`
- Place all SQLModel table models in `wiregui/models/`
- Place Pydantic request/response schemas in `wiregui/schemas/`
- Use Alembic autogenerate for migrations
- Background tasks use asyncio (create_task + while/sleep pattern)
- WireGuard/nftables managed via subprocess (asyncio.create_subprocess_exec)
- DB is source of truth; WG/firewall state is reconciled on startup

## Logging — MANDATORY
- **Use loguru for ALL logging and messages. No `print()` statements allowed anywhere in this project.**
- Import: `from loguru import logger`
- Use `logger.info()`, `logger.warning()`, `logger.error()`, `logger.debug()`, etc.
- Loguru is configured in `wiregui/logging.py` via `setup_logging()`
- When `WG_LOG_TO_FILE=true` (default), timestamped log files are written to `logs/` in the project root
- The `logs/` directory is gitignored

## Testing
- Tests live in `tests/` mirroring the `wiregui/` structure
- Run with `uv run pytest`
- Use `pytest-asyncio` for async tests
- Test database: uses same Postgres instance, separate `wiregui_test` database

## Git Commits
- **Never** add `Co-Authored-By` lines or any AI attribution to commit messages
- Follow conventional commits format (fix:, feat:, chore:, etc.) matching existing history
