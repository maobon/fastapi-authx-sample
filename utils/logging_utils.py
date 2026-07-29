import logging
import re


class TokenMaskFilter(logging.Filter):
    """日志过滤器：去除日志输出中的敏感 token 信息。"""

    def filter(self, record):
        # 掩盖消息字符串中的 token
        if isinstance(record.msg, str):
            record.msg = self._mask_token(record.msg)

        # 掩盖参数中的 token (uvicorn 访问日志通常在 args 中)
        if record.args:
            new_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    new_args.append(self._mask_token(arg))
                else:
                    new_args.append(arg)
            record.args = tuple(new_args)
        return True

    @staticmethod
    def _mask_token(text: str) -> str:
        # 匹配 token=... 直到遇到 &, 空格, 或者行尾
        return re.sub(r"token=[^& \s]+", "token=***", text)


def setup_logging():
    """配置 uvicorn 访问日志，应用 token 掩码。"""
    logger = logging.getLogger("uvicorn.access")
    # 避免重复添加过滤器
    if not any(isinstance(f, TokenMaskFilter) for f in logger.filters):
        logger.addFilter(TokenMaskFilter())
