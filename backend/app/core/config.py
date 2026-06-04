from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Creator Monitoring API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"

    mysql_database: str = "creator_monitoring"
    mysql_user: str = "monitoring"
    mysql_password: str = "monitoring_password"
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 13306

    redis_host: str = "127.0.0.1"
    redis_port: int = 16379
    redis_db: int = 0
    cors_origins: str = "http://localhost:5174,http://127.0.0.1:5174"

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
