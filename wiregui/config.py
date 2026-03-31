from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WG_", env_file=".env")

    # Database
    database_url: str = "postgresql+asyncpg://wiregui:wiregui@localhost/wiregui"

    # Redis / Valkey
    redis_url: str = "redis://localhost:6379/0"

    # Secret key for JWT signing and Fernet encryption
    secret_key: str = "change-me-in-production"

    # WireGuard
    wg_enabled: bool = False  # set True in production (requires NET_ADMIN capability)
    wg_interface: str = "wg0"
    wg_endpoint_host: str = "localhost"
    wg_endpoint_port: int = 51820
    wg_ipv4_network: str = "10.3.2.0/24"
    wg_ipv6_network: str = "fd00::3:2:0/120"
    wg_dns: str = "1.1.1.1, 1.0.0.1"
    wg_mtu: int = 1280
    wg_persistent_keepalive: int = 25
    wg_allowed_ips: str = "0.0.0.0/0, ::/0"

    # Auth
    admin_email: str = "admin@localhost"
    admin_password: str | None = None
    local_auth_enabled: bool = True
    magic_link_enabled: bool = True
    vpn_session_duration: int = 0  # seconds, 0 = unlimited

    # SMTP
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "wiregui@localhost"

    # IdP provisioning
    idp_config_file: str | None = None  # path to YAML file with IdP definitions

    # Logging
    log_to_file: bool = True  # write timestamped log file to logs/ directory

    # App
    host: str = "0.0.0.0"
    port: int = 13000
    external_url: str = "http://localhost:13000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
