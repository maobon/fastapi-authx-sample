import hashlib
import hmac
import secrets


def verify_password(password: str, stored_hash: str) -> bool:
    """校验用户输入的明文密码是否匹配数据库中保存的密码哈希。"""
    try:
        algorithm, iterations, salt, expected_digest = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return hmac.compare_digest(actual_digest, expected_digest)
    except (TypeError, ValueError):
        return False


def hash_token(token: str) -> str:
    """对 token 做不可逆哈希，避免把原始 token 明文保存到数据库。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class CryptoUtils:
    """密码术工具类，集中处理密码哈希、密码校验和 token 哈希。"""

    def __init__(self, password_hash_iterations: int = 260_000):
        self.password_hash_iterations = password_hash_iterations

    def hash_password(self, password: str) -> str:
        """将明文密码加盐后哈希，数据库只保存哈希结果，不保存明文密码。"""
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            self.password_hash_iterations,
        ).hex()
        return f"pbkdf2_sha256${self.password_hash_iterations}${salt}${digest}"
