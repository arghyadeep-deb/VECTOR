"""
配置管理
统一从项目根目录的 .env 文件加载配置
"""

import os
import secrets
from dotenv import load_dotenv


def _is_production() -> bool:
    return (
        os.environ.get("FLASK_ENV", "").strip().lower() in {"production", "prod", "vector"}
        or os.environ.get("VECTOR_ENV", "").strip().lower() in {"production", "prod", "vector"}
    )

# VECTOR env-var aliases: map VECTOR's standard API keys into the names
# this service expects, without changing any other file.
if os.environ.get("OPENAI_API_KEY") and not os.environ.get("LLM_API_KEY"):
    os.environ["LLM_API_KEY"] = os.environ["OPENAI_API_KEY"]
if os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("LLM_API_KEY"):
    # Anthropic not OpenAI-compatible here — user must set LLM_API_KEY explicitly
    pass

# 加载项目根目录的 .env 文件
# 路径: VECTOR Social Sim/.env (相对于 backend/app/config.py)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=False)
else:
    # 如果根目录没有 .env，尝试加载环境变量（用于生产环境）
    load_dotenv(override=False)


class Config:
    """Flask配置类"""

    IS_PRODUCTION = _is_production()

    # Flask security:
    #  - No hardcoded production secret. In production SECRET_KEY MUST come from
    #    the environment (validate_security() flags it if missing). In dev we use
    #    a per-process random key so sessions still work without a known constant.
    #  - DEBUG defaults to false; only an explicit FLASK_DEBUG=true enables it.
    SECRET_KEY = os.environ.get('SECRET_KEY') or ('' if IS_PRODUCTION else secrets.token_hex(32))
    DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'

    # CORS origins: explicit comma-separated list. Wildcard is dev-only.
    CORS_ORIGINS = [o.strip() for o in os.environ.get('CORS_ORIGINS', '').split(',') if o.strip()]
    
    # JSON配置 - 禁用ASCII转义，让中文直接显示（而不是 \uXXXX 格式）
    JSON_AS_ASCII = False
    
    # LLM配置（统一使用OpenAI格式）
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')
    
    # Zep配置
    ZEP_API_KEY = os.environ.get('ZEP_API_KEY')
    
    # 文件上传配置
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}
    
    # 文本处理配置
    DEFAULT_CHUNK_SIZE = 500  # 默认切块大小
    DEFAULT_CHUNK_OVERLAP = 50  # 默认重叠大小
    
    # OASIS模拟配置
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')
    
    # OASIS平台可用动作配置
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]
    
    # Report Agent配置
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))
    
    @classmethod
    def cors_resource_origins(cls):
        """Origins for flask_cors. Explicit list in production; '*' only in dev."""
        if cls.CORS_ORIGINS:
            return cls.CORS_ORIGINS
        return "*" if not cls.IS_PRODUCTION else []

    @classmethod
    def validate_security(cls):
        """Security-critical config checks. Returns a list of errors (empty = ok).

        In production a missing SECRET_KEY or wildcard/empty CORS is rejected.
        """
        errors = []
        if cls.IS_PRODUCTION:
            if not cls.SECRET_KEY:
                errors.append("SECRET_KEY 未配置（生产环境必须设置）")
            if not cls.CORS_ORIGINS:
                errors.append("CORS_ORIGINS 未配置（生产环境不允许通配 *）")
            if cls.DEBUG:
                errors.append("FLASK_DEBUG 不能在生产环境启用")
        return errors

    @classmethod
    def validate(cls):
        """验证必要配置"""
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY 未配置")
        if not cls.ZEP_API_KEY:
            errors.append("ZEP_API_KEY 未配置")
        return errors

