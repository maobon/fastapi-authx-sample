import os
from minio import Minio
from constant import (
    DEFAULT_MINIO_ENDPOINT,
    DEFAULT_MINIO_ACCESS_KEY,
    DEFAULT_MINIO_SECRET_KEY,
    DEFAULT_MINIO_BUCKET,
)

# MinIO 配置读取
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", DEFAULT_MINIO_ENDPOINT)
if MINIO_ENDPOINT.startswith("http://"):
    MINIO_ENDPOINT = MINIO_ENDPOINT[7:]
elif MINIO_ENDPOINT.startswith("https://"):
    MINIO_ENDPOINT = MINIO_ENDPOINT[8:]

MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", DEFAULT_MINIO_ACCESS_KEY)
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", DEFAULT_MINIO_SECRET_KEY)
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", DEFAULT_MINIO_BUCKET)
MINIO_SECURE = os.environ.get("MINIO_SECURE", "False").lower() == "true"

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
        print(f"Error: Could not connect to MinIO or set bucket policy: {e}")
