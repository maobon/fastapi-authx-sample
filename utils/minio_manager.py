import logging
from minio import Minio
from config import settings

# MinIO 配置从 settings 中读取
MINIO_ENDPOINT = settings.get_minio_endpoint_clean()
MINIO_ACCESS_KEY = settings.minio_access_key
MINIO_SECRET_KEY = settings.minio_secret_key
MINIO_BUCKET = settings.minio_bucket
MINIO_SECURE = settings.minio_secure

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE,
)


def get_public_readonly_policy(bucket_name: str) -> str:
    """获取公开只读策略。"""
    return f"""{{
      "Version": "2012-10-17",
      "Statement": [
        {{
          "Effect": "Allow",
          "Principal": {{"AWS": ["*"]}},
          "Action": ["s3:GetObject"],
          "Resource": ["arn:aws:s3:::{bucket_name}/*"]
        }}
      ]
    }}"""


def ensure_bucket_exists(bucket_name: str):
    """确保 MinIO Bucket 存在并设置为公开只读。"""
    try:
        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)

        policy = get_public_readonly_policy(bucket_name)
        minio_client.set_bucket_policy(bucket_name, policy)
    except Exception as e:
        logging.error(f"Could not connect to MinIO or set bucket policy: {e}")
