from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from config import Config


# 单例形式创建系统库 sql_exam_sys 的 Engine，用于读写用户、题目和做题记录等核心业务数据。
# 启用 pool_pre_ping，在连接从连接池取出前先做一次心跳，避免 MySQL 长时间空闲后断开导致的 2013 错误。
exam_engine = create_engine(Config.exam_db_url(), future=True, pool_pre_ping=True)


def get_exam_engine() -> Engine:
    """返回连接系统库 sql_exam_sys 的 engine。

    说明：
    - 使用管理员账号（可写），仅在业务逻辑中更新 users / questions / records / datasets 等表。
    - 不在此 engine 上执行用户提交的 SQL，避免安全风险。
    """

    return exam_engine


@lru_cache(maxsize=8)
def get_dataset_engine(db_name: str) -> Engine:
    """根据靶场库库名创建并缓存只读 engine。

    参数：
    - db_name: 数据集对应的物理库名，如 "ds_student_scores"、"ds_ecommerce_orders" 等。

    说明：
    - 使用只读账号连接，确保用户练习的 SQL 只能做 SELECT，不会破坏数据。
    - 使用 lru_cache 避免为同一个库重复创建连接池。
    """

    url = (
        f"mysql+pymysql://{Config.MYSQL_READONLY_USER}:{Config.MYSQL_READONLY_PASSWORD}"
        f"@{Config.MYSQL_HOST}:{Config.MYSQL_PORT}/{db_name}?charset=utf8mb4"
    )
    # 对靶场库的只读连接同样开启 pool_pre_ping，减少空闲连接被 MySQL 回收后造成的断连问题。
    return create_engine(url, future=True, pool_pre_ping=True)

