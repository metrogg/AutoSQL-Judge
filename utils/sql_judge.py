import pandas as pd

from utils.db import get_dataset_engine


def judge_sql(
    user_sql: str,
    standard_sql: str,
    dataset_db_name: str = "ds_student_scores",
) -> dict:
    """在指定靶场库中执行并比对两条 SQL 的结果集。

    参数：
    - user_sql: 用户提交的 SQL 语句。
    - standard_sql: 标准答案 SQL 语句（由老师或 LLM 生成）。
    - dataset_db_name: 数据集所在的物理库名，例如 "ds_student_scores"。

    判题规则：
    1. 在同一个只读数据库连接上，分别执行 standard_sql 和 user_sql。
    2. 将查询结果加载为 Pandas DataFrame。
    3. 按所有列排序并 reset_index，忽略行顺序差异。
    4. 使用 DataFrame.equals 做严格相等比较（列名 + 数据完全一致）。

    返回：字典结构，例如：
    - {"status": "success", "msg": "恭喜！答案正确！"}
    - {"status": "fail", "msg": "结果不一致，请检查逻辑。"}
    - {"status": "error", "msg": "SQL 语法错误信息或其他异常"}
    """

    try:
        # 按数据集库名获取只读 engine，不同业务场景会连到不同的 ds_* 库。
        engine = get_dataset_engine(dataset_db_name)

        # 执行标准答案和用户答案，分别获取结果集。
        df_std = pd.read_sql(standard_sql, engine)
        df_user = pd.read_sql(user_sql, engine)

        # 统一排序并重置索引，忽略结果集的行顺序影响，只关注数据内容本身。
        df_std = df_std.sort_values(by=df_std.columns.tolist()).reset_index(drop=True)
        df_user_sorted = df_user.sort_values(by=df_user.columns.tolist()).reset_index(drop=True)

        # 准备用户结果预览（前 5 行），用于前端展示
        preview_data = {
            "columns": df_user.columns.tolist(),
            "rows": df_user.head(5).astype(str).values.tolist(),  # 转字符串避免序列化问题
            "total_rows": len(df_user),
        }

        if df_std.equals(df_user_sorted):
            return {
                "status": "success",
                "msg": "恭喜！答案正确！",
                "preview": preview_data,
            }

        return {
            "status": "fail",
            "msg": "结果不一致，请检查逻辑。",
            "preview": preview_data,
        }

    except Exception as exc:  # noqa: BLE001
        # 捕获数据库执行或 Pandas 处理中的异常，返回给前端展示。
        return {"status": "error", "msg": str(exc)}

