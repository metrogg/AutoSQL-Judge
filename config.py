import os

from dotenv import load_dotenv


load_dotenv()


class Config:
    """Flask 应用和数据库连接的集中配置。

    说明：
    - 敏感信息优先从环境变量读取，默认值只用于本地开发调试。
    - 系统库使用管理员账号（可写），靶场库通过只读账号访问（在 utils/db.py 中使用）。
    """

    # Flask 会话密钥，用于签名 Cookie 等。正式环境请从环境变量中注入随机值。
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

    # MySQL 基础连接信息（主机和端口）。
    MYSQL_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT = int(os.environ.get("MYSQL_PORT", 3306))

    # 管理员账号：用于连接系统库 sql_exam_sys，写入用户、题目和做题记录等数据。
    MYSQL_ADMIN_USER = os.environ.get("MYSQL_ADMIN_USER", "root")
    MYSQL_ADMIN_PASSWORD = os.environ.get("MYSQL_ADMIN_PASSWORD", "root")

    # 只读账号：用于连接各个靶场库 ds_*，只授予 SELECT 权限，防止练习 SQL 误删数据。
    MYSQL_READONLY_USER = os.environ.get("MYSQL_READONLY_USER", "readonly_user")
    MYSQL_READONLY_PASSWORD = os.environ.get("MYSQL_READONLY_PASSWORD", "1234")

    # 系统库名称：所有用户、题目、做题记录和 datasets 配置都存放在该库中。
    EXAM_DB_NAME = os.environ.get("EXAM_DB_NAME", "sql_exam_sys")

    # 大模型 API 配置：用于基于 Schema 自动生成 SQL 题目等能力。
    # 示例：
    #   LLM_API_BASE=https://api.openai.com
    #   LLM_API_KEY=sk-xxx
    #   LLM_MODEL=gpt-4o-mini
    LLM_API_BASE = os.environ.get("LLM_API_BASE", "")
    LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
    LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")

    @classmethod
    def exam_db_url(cls) -> str:
        """构造连接系统库 sql_exam_sys 的 SQLAlchemy URL（使用管理员账号）。"""
        return (
            f"mysql+pymysql://{cls.MYSQL_ADMIN_USER}:{cls.MYSQL_ADMIN_PASSWORD}"
            f"@{cls.MYSQL_HOST}:{cls.MYSQL_PORT}/{cls.EXAM_DB_NAME}?charset=utf8mb4"
        )
