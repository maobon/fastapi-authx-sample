import re

USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,149}$")
PASSWORD_PATTERN = re.compile(r"^[^\s]{8,128}$")


def validate_username(username: str) -> str:
    """校验用户名，确保进入数据库前是规范的业务标识。"""
    normalized_username = username.strip()
    if not USERNAME_PATTERN.fullmatch(normalized_username):
        raise ValueError(
            "Username must start with a letter and contain only letters, numbers, or underscores; length 3-150"
        )
    return normalized_username


def validate_password(password: str) -> str:
    """校验密码，拒绝空白字符和明显无效的弱输入。"""
    if not PASSWORD_PATTERN.fullmatch(password):
        raise ValueError("Password must be 8-128 characters and must not contain whitespace")
    if password.isdigit() or password.isalpha():
        raise ValueError("Password must contain at least two character types")
    return password


def validate_login_password(password: str) -> str:
    """登录场景只做格式边界校验，避免绕过请求层传入明显非法输入。"""
    if not password or len(password) > 128 or any(character.isspace() for character in password):
        raise ValueError("Password must be 1-128 characters and must not contain whitespace")
    return password
