from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    项目全局配置类，基于 Pydantic Settings 实现。
    自动从环境变量中读取配置，并支持 .env 文件。
    """

    # 数据库配置
    database_url: str = "postgresql://postgres:@127.0.0.1:5432/myapp"
    disable_db_pool: bool = False

    # 认证配置
    jwt_secret_key: str = "dev-only-change-me-32-byte-secret-key"

    # MinIO 配置
    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "images"
    minio_secure: bool = False

    # 服务器配置
    port: int = 8000

    # Pydantic Settings 配置
    model_config = SettingsConfigDict(
        env_file=".env",
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


settings = Settings()
