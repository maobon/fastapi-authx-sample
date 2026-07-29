import json
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    项目全局配置类，基于 Pydantic Settings 实现。
    配置信息从 config.json 文件中读取。
    """

    # 数据库配置
    database_url: str
    disable_db_pool: bool

    # 认证配置
    jwt_secret_key: str

    # MinIO 配置
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_secure: bool
    minio_public_host: str

    # 服务器配置
    port: int

    # Pydantic Settings 配置
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_minio_endpoint_clean(self) -> str:
        """返回不带协议头的 MinIO Endpoint。"""
        endpoint = self.minio_endpoint
        if endpoint.startswith("http://"):
            return endpoint[7:]
        if endpoint.startswith("https://"):
            return endpoint[8:]
        return endpoint


def load_settings() -> Settings:
    config_path = Path(__file__).parent / "config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        return Settings(**config_data)
    else:
        raise FileNotFoundError(f"Configuration file not found at {config_path}")


settings = load_settings()
