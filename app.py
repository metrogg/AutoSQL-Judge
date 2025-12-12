from flask import Flask, jsonify, render_template, request, session, redirect
from time import perf_counter

from config import Config
from utils.db import get_exam_engine, get_dataset_engine
from utils.sql_judge import judge_sql
from utils.llm_client import (
    LLMError,
    generate_sql_question_from_schema,
    admin_llm_chat,
    explain_sql_answer,
)
from werkzeug.security import check_password_hash, generate_password_hash


def create_app() -> Flask:
    """应用工厂：创建并配置 Flask 实例。

    当前阶段：
    - 仅提供一个首页和 /health 健康检查接口，用于验证环境与配置是否正确。
    - 后续会在此函数中注册更多蓝图（题目生成、判题 API 等）。
    """

    app = Flask(__name__)
    # 从 Config 类加载数据库等配置信息。
    app.config.from_object(Config)

    @app.route("/")
    def index():
        """主页：后续挂载前端单页（Vue + Bootstrap）。"""
        return render_template("index.html")

    @app.route("/health")
    def health():
        """健康检查接口：用于确认服务是否正常运行。"""
        return jsonify({"status": "ok"})

    @app.route("/api/auth/register", methods=["POST"])
    def api_auth_register():
        """用户注册接口：创建新用户并自动登录。"""

        data = request.get_json(silent=True) or {}
        username = (data.get("username") or "").strip()
        password = (data.get("password") or "").strip()

        if not username or not password:
            return (
                jsonify(
                    {
                        "status": "error",
                        "msg": "用户名和密码均为必填项。",
                    }
                ),
                400,
            )

        if len(username) < 3 or len(password) < 4:
            return (
                jsonify(
                    {
                        "status": "error",
                        "msg": "用户名至少 3 个字符，密码至少 4 个字符。",
                    }
                ),
                400,
            )

        # 当前登录用户 ID（未登录则为 None，后续会按 0 记匿名练习）
        user_id = session.get("user_id")

        try:
            with get_exam_engine().begin() as conn:
                existed = conn.exec_driver_sql(
                    "SELECT id FROM users WHERE username = %s",
                    (username,),
                ).fetchone()
                if existed:
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "msg": "用户名已存在，请直接登录或更换用户名。",
                            }
                        ),
                        400,
                    )

                pwd_hash = generate_password_hash(password)
                result = conn.exec_driver_sql(
                    """
                    INSERT INTO users (username, password_hash, total_score, created_at)
                    VALUES (%s, %s, %s, NOW())
                    """,
                    (username, pwd_hash, 0),
                )
                user_id = result.lastrowid
        except Exception as exc:  # noqa: BLE001
            return jsonify({"status": "error", "msg": f"注册失败: {exc}"}), 500

        session["user_id"] = user_id
        session["username"] = username

        return jsonify(
            {
                "status": "success",
                "data": {"user_id": user_id, "username": username, "total_score": 0},
            }
        )

    @app.route("/api/auth/login", methods=["POST"])
    def api_auth_login():
        """用户登录接口：验证用户名密码并写入会话。"""

        data = request.get_json(silent=True) or {}
        username = (data.get("username") or "").strip()
        password = (data.get("password") or "").strip()

        if not username or not password:
            return (
                jsonify(
                    {
                        "status": "error",
                        "msg": "用户名和密码均为必填项。",
                    }
                ),
                400,
            )

        try:
            with get_exam_engine().connect() as conn:
                row = conn.exec_driver_sql(
                    "SELECT id, password_hash, COALESCE(total_score, 0) FROM users WHERE username = %s",
                    (username,),
                ).fetchone()
        except Exception as exc:  # noqa: BLE001
            return jsonify({"status": "error", "msg": f"登录失败: {exc}"}), 500

        if not row:
            return (
                jsonify(
                    {
                        "status": "error",
                        "code": "USER_NOT_FOUND",
                        "msg": "用户不存在，请检查用户名或先注册。",
                    }
                ),
                400,
            )

        user_id, password_hash, total_score = row

        if not check_password_hash(password_hash, password):
            return (
                jsonify(
                    {
                        "status": "error",
                        "code": "INVALID_PASSWORD",
                        "msg": "密码错误，请重试。",
                    }
                ),
                400,
            )

        session["user_id"] = user_id
        session["username"] = username

        return jsonify(
            {
                "status": "success",
                "data": {
                    "user_id": user_id,
                    "username": username,
                    "total_score": total_score,
                },
            }
        )

    @app.route("/api/auth/logout", methods=["POST"])
    def api_auth_logout():
        """退出登录：清理会话信息。"""

        session.pop("user_id", None)
        session.pop("username", None)
        return jsonify({"status": "success"})

    @app.route("/api/auth/me", methods=["GET"])
    def api_auth_me():
        """获取当前登录用户信息，用于前端展示用户名与总分。"""

        user_id = session.get("user_id")
        username = session.get("username")
        if not user_id or not username:
            return jsonify({"status": "success", "data": None})

        try:
            with get_exam_engine().connect() as conn:
                row = conn.exec_driver_sql(
                    "SELECT COALESCE(total_score, 0) FROM users WHERE id = %s",
                    (user_id,),
                ).fetchone()
        except Exception as exc:  # noqa: BLE001
            return jsonify({"status": "error", "msg": f"读取用户信息失败: {exc}"}), 500

        if not row:
            # 会话中记录的用户在库中不存在，视为未登录
            session.pop("user_id", None)
            session.pop("username", None)
            return jsonify({"status": "success", "data": None})

        total_score = row[0]
        return jsonify(
            {
                "status": "success",
                "data": {
                    "user_id": user_id,
                    "username": username,
                    "total_score": total_score,
                },
            }
        )

    @app.route("/admin")
    def admin_dashboard():
        """简易后台：展示题目、提交记录、学生统计和 LLM 调用日志。"""

        dataset_key = (request.args.get("dataset_key") or "").strip() or None
        result_filter = (request.args.get("result") or "").strip() or None
        user_id_raw = (request.args.get("user_id") or "").strip()
        user_id_filter: int | None = None
        if user_id_raw:
            try:
                user_id_filter = int(user_id_raw)
            except ValueError:
                user_id_filter = None

        try:
            with get_exam_engine().connect() as conn:
                # 题目列表（可按数据集过滤）
                q_sql = (
                    "SELECT q.id, q.title, q.difficulty, q.score, q.source, d.`key` AS dataset_key, q.created_at "
                    "FROM questions q "
                    "LEFT JOIN datasets d ON q.dataset_id = d.id"
                )
                q_params: list[object] = []
                if dataset_key:
                    q_sql += " WHERE d.`key` = %s"
                    q_params.append(dataset_key)
                q_sql += " ORDER BY q.created_at DESC LIMIT 50"
                questions = conn.exec_driver_sql(q_sql, tuple(q_params)).fetchall()

                # 提交记录（可按用户、结果、数据集过滤）
                r_sql = (
                    "SELECT id, user_id, question_id, result, score, exec_time, created_at "
                    "FROM records WHERE 1=1"
                )
                r_params: list[object] = []
                if user_id_filter is not None:
                    r_sql += " AND user_id = %s"
                    r_params.append(user_id_filter)
                if result_filter:
                    r_sql += " AND result = %s"
                    r_params.append(result_filter)
                if dataset_key:
                    r_sql += (
                        " AND dataset_id = (SELECT id FROM datasets WHERE `key` = %s LIMIT 1)"
                    )
                    r_params.append(dataset_key)
                r_sql += " ORDER BY created_at DESC LIMIT 50"
                records = conn.exec_driver_sql(r_sql, tuple(r_params)).fetchall()

                # 学生概览统计
                users_stats = conn.exec_driver_sql(
                    """
                    SELECT
                        u.id,
                        u.username,
                        COALESCE(u.total_score, 0) AS total_score,
                        COALESCE(SUM(CASE WHEN r.result = 'Pass' THEN 1 ELSE 0 END), 0) AS passed_count,
                        COUNT(r.id) AS submit_count,
                        MAX(r.created_at) AS last_submit_at
                    FROM users u
                    LEFT JOIN records r ON r.user_id = u.id
                    GROUP BY u.id, u.username, u.total_score
                    ORDER BY total_score DESC, submit_count DESC, u.id ASC
                    LIMIT 50
                    """
                ).fetchall()

                # LLM 调用日志（若表不存在则忽略）
                try:
                    llm_logs = conn.exec_driver_sql(
                        """
                        SELECT id, dataset_key, dataset_id, difficulty, status, error_message, latency_ms, created_at
                        FROM llm_calls
                        ORDER BY created_at DESC
                        LIMIT 50
                        """
                    ).fetchall()
                except Exception:  # noqa: BLE001
                    llm_logs = []
        except Exception as exc:  # noqa: BLE001
            return jsonify({"status": "error", "msg": f"加载后台数据失败: {exc}"}), 500

        return render_template(
            "admin.html",
            questions=questions,
            records=records,
            users_stats=users_stats,
            llm_logs=llm_logs,
            dataset_key_filter=dataset_key or "",
            result_filter=result_filter or "",
            user_id_filter=user_id_raw,
        )

    @app.route("/admin/questions/update_source", methods=["POST"])
    def admin_update_question_source():
        """后台：手动调整题目来源（db / llm）。"""

        qid_raw = request.form.get("question_id")
        source = (request.form.get("source") or "db").strip()
        next_url = request.form.get("next") or "/admin"

        try:
            qid = int(qid_raw)
        except (TypeError, ValueError):  # noqa: PERF203
            return redirect(next_url)

        if source not in {"db", "llm"}:
            source = "db"

        try:
            with get_exam_engine().begin() as conn:
                conn.exec_driver_sql(
                    "UPDATE questions SET source = %s WHERE id = %s",
                    (source, qid),
                )
        except Exception:  # noqa: BLE001
            # 更新失败时先不打断页面流程，仍然返回后台页
            return redirect(next_url)

        return redirect(next_url)

    @app.route("/admin/questions/delete", methods=["POST"])
    def admin_delete_question():
        """后台：删除单条题目记录。"""

        qid_raw = request.form.get("question_id")
        next_url = request.form.get("next") or "/admin"

        try:
            qid = int(qid_raw)
        except (TypeError, ValueError):  # noqa: PERF203
            return redirect(next_url)

        try:
            with get_exam_engine().begin() as conn:
                conn.exec_driver_sql("DELETE FROM questions WHERE id = %s", (qid,))
        except Exception:  # noqa: BLE001
            # 删除失败也不阻断页面
            return redirect(next_url)

        return redirect(next_url)

    @app.route("/admin/questions/dedup", methods=["POST"])
    def admin_dedup_questions():
        """后台：按 dataset_id + title + standard_sql 清理重复题目，保留每组 id 最小的一条。"""

        next_url = request.form.get("next") or "/admin"

        try:
            with get_exam_engine().begin() as conn:
                conn.exec_driver_sql(
                    """
                    DELETE q1
                    FROM questions q1
                    JOIN questions q2
                      ON q1.dataset_id = q2.dataset_id
                     AND q1.title = q2.title
                     AND q1.standard_sql = q2.standard_sql
                     AND q1.id > q2.id
                    """
                )
        except Exception:
            return redirect(next_url)

        return redirect(next_url)

    @app.route("/admin/questions/edit")
    def admin_edit_question():
        qid_raw = request.args.get("id")
        question = None
        dataset_key = ""

        try:
            qid = int(qid_raw) if qid_raw else None
        except (TypeError, ValueError):
            return redirect("/admin")

        if qid is not None:
            try:
                with get_exam_engine().connect() as conn:
                    # 确保存在答案查看控制字段
                    try:
                        conn.exec_driver_sql(
                            "ALTER TABLE questions ADD COLUMN allow_view_answer TINYINT(1) NOT NULL DEFAULT 0"
                        )
                    except Exception:  # noqa: BLE001
                        pass

                    row = conn.exec_driver_sql(
                        """
                        SELECT
                            q.id,
                            q.title,
                            q.standard_sql,
                            q.difficulty,
                            q.score,
                            q.dataset_id,
                            COALESCE(q.source, 'db') AS source,
                            COALESCE(q.allow_view_answer, 0) AS allow_view_answer,
                            q.created_at,
                            d.`key` AS dataset_key
                        FROM questions q
                        LEFT JOIN datasets d ON q.dataset_id = d.id
                        WHERE q.id = %s
                        """,
                        (qid,),
                    ).fetchone()
            except Exception:  # noqa: BLE001
                row = None

            if not row:
                return redirect("/admin")

            question = row
            dataset_key = row.dataset_key
        else:
            dataset_key = request.args.get("dataset_key", "student_scores") or "student_scores"

        return render_template(
            "admin_question_edit.html",
            question=question,
            dataset_key=dataset_key,
        )

    @app.route("/admin/questions/save", methods=["POST"])
    def admin_save_question():
        qid_raw = request.form.get("question_id")
        dataset_key = (request.form.get("dataset_key") or "").strip()
        title = (request.form.get("title") or "").strip()
        standard_sql = (request.form.get("standard_sql") or "").strip()
        difficulty = (request.form.get("difficulty") or "").strip() or "Medium"
        score_raw = request.form.get("score")
        allow_view_answer_flag = bool(request.form.get("allow_view_answer"))
        next_url = request.form.get("next") or "/admin"

        try:
            score = int(score_raw) if score_raw not in {None, ""} else 10
        except (TypeError, ValueError):
            score = 10

        if not dataset_key or not title or not standard_sql:
            return redirect(next_url)

        try:
            qid = int(qid_raw) if qid_raw else None
        except (TypeError, ValueError):
            qid = None

        try:
            with get_exam_engine().begin() as conn:
                # 确保存在答案查看控制字段
                try:
                    conn.exec_driver_sql(
                        "ALTER TABLE questions ADD COLUMN allow_view_answer TINYINT(1) NOT NULL DEFAULT 0"
                    )
                except Exception:  # noqa: BLE001
                    pass

                ds_row = conn.exec_driver_sql(
                    "SELECT id FROM datasets WHERE `key` = %s AND is_active = 1",
                    (dataset_key,),
                ).fetchone()
                if not ds_row:
                    return redirect(next_url)
                dataset_id = ds_row[0]

                if qid:
                    conn.exec_driver_sql(
                        """
                        UPDATE questions
                        SET title = %s,
                            standard_sql = %s,
                            difficulty = %s,
                            score = %s,
                            dataset_id = %s,
                            allow_view_answer = %s
                        WHERE id = %s
                        """,
                        (title, standard_sql, difficulty, score, dataset_id, int(allow_view_answer_flag), qid),
                    )
                else:
                    conn.exec_driver_sql(
                        """
                        INSERT INTO questions (title, standard_sql, difficulty, score, dataset_id, source, allow_view_answer, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                        """,
                        (title, standard_sql, difficulty, score, dataset_id, "db", int(allow_view_answer_flag)),
                    )
        except Exception:
            return redirect(next_url)

        return redirect(next_url)

    @app.route("/api/admin/llm_generate_question", methods=["POST"])
    def api_admin_llm_generate_question():
        data = request.get_json(silent=True) or {}
        dataset_key = (data.get("dataset_key") or "student_scores").strip() or "student_scores"
        difficulty = (data.get("difficulty") or "").strip() or None
        require_join = bool(data.get("require_join"))
        require_group_by = bool(data.get("require_group_by"))
        require_subquery = bool(data.get("require_subquery"))
        business_hint = (data.get("business_hint") or "").strip()
        extra_constraints = (data.get("extra_constraints") or "").strip()

        try:
            with get_exam_engine().connect() as conn:
                ds_row = conn.exec_driver_sql(
                    "SELECT id, `key`, db_name, COALESCE(schema_desc, '') "
                    "FROM datasets WHERE `key` = %s AND is_active = 1",
                    (dataset_key,),
                ).fetchone()
                if not ds_row:
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "msg": f"未找到数据集: {dataset_key}",
                            }
                        ),
                        400,
                    )

                dataset_id, dataset_key_db, dataset_db_name, schema_desc = ds_row

                schema_text = schema_desc or ""
                if not schema_text:
                    try:
                        with get_dataset_engine(dataset_db_name).connect() as ds_conn:
                            rows = ds_conn.exec_driver_sql(
                                """
                                SELECT table_name, column_name, data_type
                                FROM information_schema.columns
                                WHERE table_schema = %s
                                ORDER BY table_name, ordinal_position
                                """,
                                (dataset_db_name,),
                            ).fetchall()
                    except Exception as exc:  # noqa: BLE001
                        return (
                            jsonify(
                                {
                                    "status": "error",
                                    "msg": f"读取数据集表结构失败: {exc}",
                                }
                            ),
                            500,
                        )

                    lines: list[str] = []
                    current_table: str | None = None
                    for table_name, column_name, data_type in rows:
                        if table_name != current_table:
                            current_table = table_name
                            lines.append(f"表 {table_name}:")
                        lines.append(f"  - {column_name} ({data_type})")
                    schema_text = "\n".join(lines)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"status": "error", "msg": f"准备 LLM 上下文失败: {exc}"}), 500

        hint_parts: list[str] = []
        if business_hint:
            hint_parts.append(f"业务场景或出题方向: {business_hint}")
        if extra_constraints:
            hint_parts.append(f"额外出题要求: {extra_constraints}")
        if require_join:
            hint_parts.append("题目必须涉及至少两个表的 JOIN 联合查询，避免仅单表查询。")
        if require_group_by:
            hint_parts.append("题目需要使用 GROUP BY 聚合统计。")
        if require_subquery:
            hint_parts.append("题目尽量包含子查询或嵌套 SELECT 等进阶用法。")

        user_hint = "；".join(hint_parts) if hint_parts else None

        try:
            q_obj = generate_sql_question_from_schema(
                dataset_key=dataset_key_db,
                schema_text=schema_text,
                difficulty=difficulty,
                user_hint=user_hint,
            )
        except LLMError as exc:  # noqa: BLE001
            return (
                jsonify(
                    {
                        "status": "error",
                        "msg": f"调用大模型生成题目失败: {exc}",
                    }
                ),
                500,
            )

        return jsonify(
            {
                "status": "success",
                "data": {
                    "dataset_key": dataset_key_db,
                    "question": q_obj,
                },
            }
        )

    @app.route("/api/admin/llm_chat", methods=["POST"])
    def api_admin_llm_chat():
        data = request.get_json(silent=True) or {}
        message = (data.get("message") or "").strip()

        if not message:
            return (
                jsonify(
                    {
                        "status": "error",
                        "msg": "消息内容不能为空。",
                    }
                ),
                400,
            )

        context_text = ""
        try:
            with get_exam_engine().connect() as conn:
                q_total_row = conn.exec_driver_sql(
                    "SELECT COUNT(*) FROM questions"
                ).fetchone()
                q_total = q_total_row[0] if q_total_row else 0

                user_total_row = conn.exec_driver_sql(
                    "SELECT COUNT(*) FROM users"
                ).fetchone()
                user_total = user_total_row[0] if user_total_row else 0

                record_total_row = conn.exec_driver_sql(
                    "SELECT COUNT(*) FROM records"
                ).fetchone()
                record_total = record_total_row[0] if record_total_row else 0

                llm_total = 0
                try:
                    llm_total_row = conn.exec_driver_sql(
                        "SELECT COUNT(*) FROM llm_calls"
                    ).fetchone()
                    llm_total = llm_total_row[0] if llm_total_row else 0
                except Exception:
                    llm_total = 0

            context_text = (
                "系统当前的粗略数据统计：\n"
                f"- 题目总数: {q_total}\n"
                f"- 注册用户数: {user_total}\n"
                f"- 判题提交总数: {record_total}\n"
                f"- LLM 出题调用次数: {llm_total}\n"
            )
        except Exception:
            context_text = ""

        try:
            reply = admin_llm_chat(message, extra_context=context_text)
        except LLMError as exc:
            return (
                jsonify(
                    {
                        "status": "error",
                        "msg": f"调用后台 LLM 助手失败: {exc}",
                    }
                ),
                500,
            )

        return jsonify({"status": "success", "data": {"reply": reply}})

    @app.route("/api/dataset/preview", methods=["GET"])
    def api_dataset_preview():
        """返回指定数据集下各个表的少量示例数据，便于学生在前端查看。"""

        dataset_key = request.args.get("dataset_key", "student_scores")

        try:
            with get_exam_engine().connect() as conn:
                ds_row = conn.exec_driver_sql(
                    "SELECT id, `key`, db_name FROM datasets WHERE `key` = %s AND is_active = 1",
                    (dataset_key,),
                ).fetchone()
                if not ds_row:
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "msg": f"未找到数据集: {dataset_key}",
                            }
                        ),
                        400,
                    )

                dataset_id, dataset_key_db, dataset_db_name = ds_row

            tables: dict[str, dict[str, object]] = {}
            with get_dataset_engine(dataset_db_name).connect() as ds_conn:
                tbl_rows = ds_conn.exec_driver_sql(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = %s
                    ORDER BY table_name
                    """,
                    (dataset_db_name,),
                ).fetchall()

                for (table_name,) in tbl_rows:
                    # 列信息
                    cols = ds_conn.exec_driver_sql(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = %s AND table_name = %s
                        ORDER BY ordinal_position
                        """,
                        (dataset_db_name, table_name),
                    ).fetchall()
                    col_names = [c[0] for c in cols]

                    # 示例数据
                    data_rows = ds_conn.exec_driver_sql(
                        f"SELECT * FROM `{table_name}` LIMIT 5"
                    ).fetchall()
                    rows_list = [list(r) for r in data_rows]

                    tables[table_name] = {"columns": col_names, "rows": rows_list}
        except Exception as exc:  # noqa: BLE001
            return jsonify({"status": "error", "msg": f"加载示例数据失败: {exc}"}), 500

        return jsonify(
            {
                "status": "success",
                "data": {"dataset_key": dataset_key_db, "tables": tables},
            }
        )

    @app.route("/api/question/generate", methods=["GET"])
    def api_question_generate():
        """获取一题。

        根据 `source` 参数决定题目来源：
        - source = "db"（默认）：从 questions 表中按条件随机抽取一题；
        - source = "llm"：基于指定数据集的表结构调用大模型实时生成一题，写入 questions 后返回。

        请求示例：
        - GET /api/question/generate?dataset_key=student_scores&difficulty=Easy
        - GET /api/question/generate?dataset_key=student_scores&source=llm
        """

        dataset_key = request.args.get("dataset_key", "student_scores")
        difficulty = request.args.get("difficulty")
        source = request.args.get("source", "db").lower()
        user_hint = request.args.get("user_hint")

        user_id = session.get("user_id")
        user_total_score: float | None = None

        try:
            with get_exam_engine().begin() as conn:
                # 1. 根据 dataset_key 找到对应的数据集配置。
                ds_row = conn.exec_driver_sql(
                    "SELECT id, `key`, db_name, COALESCE(schema_desc, '') "
                    "FROM datasets WHERE `key` = %s AND is_active = 1",
                    (dataset_key,),
                ).fetchone()

                if not ds_row:
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "msg": f"未找到数据集: {dataset_key}，请检查 datasets 表配置。",
                            }
                        ),
                        400,
                    )

                dataset_id, dataset_key_db, dataset_db_name, schema_desc = ds_row

                # 确保 questions 表存在 source 字段，用于标记题目来源（db / llm 等）。
                try:
                    conn.exec_driver_sql(
                        "ALTER TABLE questions ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT 'db'"
                    )
                except Exception:  # noqa: BLE001
                    # 字段已存在等情况直接忽略
                    pass

                # 确保 questions 表存在答案查看控制字段，用于控制学生是否可在提交后查看标准答案。
                try:
                    conn.exec_driver_sql(
                        "ALTER TABLE questions ADD COLUMN allow_view_answer TINYINT(1) NOT NULL DEFAULT 0"
                    )
                except Exception:  # noqa: BLE001
                    # 字段已存在等情况直接忽略
                    pass

                # 2. 如果 source=llm，则调用大模型生成题目并写入 questions，并记录调用日志。
                if source == "llm":
                    schema_text = schema_desc or ""

                    # 若 datasets 中未维护 schema_desc，则从 information_schema 反查表结构。
                    if not schema_text:
                        try:
                            with get_dataset_engine(dataset_db_name).connect() as ds_conn:
                                rows = ds_conn.exec_driver_sql(
                                    """
                                    SELECT table_name, column_name, data_type
                                    FROM information_schema.columns
                                    WHERE table_schema = %s
                                    ORDER BY table_name, ordinal_position
                                    """,
                                    (dataset_db_name,),
                                ).fetchall()
                        except Exception as exc:  # noqa: BLE001
                            return (
                                jsonify(
                                    {
                                        "status": "error",
                                        "msg": f"读取数据集表结构失败: {exc}",
                                    }
                                ),
                                500,
                            )

                        lines: list[str] = []
                        current_table: str | None = None
                        for table_name, column_name, data_type in rows:
                            if table_name != current_table:
                                current_table = table_name
                                lines.append(f"表 {table_name}:")
                            lines.append(f"  - {column_name} ({data_type})")
                        schema_text = "\n".join(lines)

                    llm_start = perf_counter()
                    try:
                        q_obj = generate_sql_question_from_schema(
                            dataset_key=dataset_key_db,
                            schema_text=schema_text,
                            difficulty=difficulty,
                            user_hint=user_hint,
                        )
                    except LLMError as exc:  # noqa: BLE001
                        llm_latency_ms = (perf_counter() - llm_start) * 1000
                        try:
                            conn.exec_driver_sql(
                                """
                                CREATE TABLE IF NOT EXISTS llm_calls (
                                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                                    dataset_key VARCHAR(100) NOT NULL,
                                    dataset_id BIGINT NULL,
                                    difficulty VARCHAR(32) NULL,
                                    status VARCHAR(20) NOT NULL,
                                    error_message TEXT NULL,
                                    latency_ms DOUBLE NULL,
                                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                                """
                            )
                            conn.exec_driver_sql(
                                """
                                INSERT INTO llm_calls
                                (dataset_key, dataset_id, difficulty, status, error_message, latency_ms, created_at)
                                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                                """,
                                (
                                    dataset_key_db,
                                    dataset_id,
                                    difficulty,
                                    "error",
                                    str(exc),
                                    llm_latency_ms,
                                ),
                            )
                        except Exception:  # noqa: BLE001
                            pass
                        return (
                            jsonify(
                                {
                                    "status": "error",
                                    "msg": f"调用大模型生成题目失败: {exc}",
                                }
                            ),
                            500,
                        )

                    llm_latency_ms = (perf_counter() - llm_start) * 1000

                    title = str(q_obj.get("title", "")).strip()
                    standard_sql = str(q_obj.get("standard_sql", "")).strip()
                    diff = str(q_obj.get("difficulty") or difficulty or "Medium").strip()
                    try:
                        score = int(q_obj.get("score") or 10)
                    except (TypeError, ValueError):  # noqa: PERF203
                        score = 10

                    if not title or not standard_sql:
                        err_msg = f"大模型返回的题目信息不完整: {q_obj}"
                        try:
                            conn.exec_driver_sql(
                                """
                                CREATE TABLE IF NOT EXISTS llm_calls (
                                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                                    dataset_key VARCHAR(100) NOT NULL,
                                    dataset_id BIGINT NULL,
                                    difficulty VARCHAR(32) NULL,
                                    status VARCHAR(20) NOT NULL,
                                    error_message TEXT NULL,
                                    latency_ms DOUBLE NULL,
                                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                                """
                            )
                            conn.exec_driver_sql(
                                """
                                INSERT INTO llm_calls
                                (dataset_key, dataset_id, difficulty, status, error_message, latency_ms, created_at)
                                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                                """,
                                (
                                    dataset_key_db,
                                    dataset_id,
                                    diff,
                                    "error",
                                    err_msg,
                                    llm_latency_ms,
                                ),
                            )
                        except Exception:  # noqa: BLE001
                            pass
                        return (
                            jsonify(
                                {
                                    "status": "error",
                                    "msg": err_msg,
                                }
                            ),
                            500,
                        )

                    # 写入 questions，标记来源为 llm
                    result = conn.exec_driver_sql(
                        """
                        INSERT INTO questions (title, standard_sql, difficulty, score, dataset_id, source, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        """,
                        (title, standard_sql, diff, score, dataset_id, "llm"),
                    )

                    q_id = result.lastrowid
                    if not q_id:
                        # 兜底：再查一次以确保拿到 id
                        row = conn.exec_driver_sql(
                            "SELECT id FROM questions WHERE dataset_id=%s ORDER BY id DESC LIMIT 1",
                            (dataset_id,),
                        ).fetchone()
                        q_id = row[0] if row else None

                    if not q_id:
                        return (
                            jsonify(
                                {
                                    "status": "error",
                                    "msg": "题目已写入，但未能获取题目 ID。",
                                }
                            ),
                            500,
                        )

                    # 记录成功日志（若表不存在则自动创建）
                    try:
                        conn.exec_driver_sql(
                            """
                            CREATE TABLE IF NOT EXISTS llm_calls (
                                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                                dataset_key VARCHAR(100) NOT NULL,
                                dataset_id BIGINT NULL,
                                difficulty VARCHAR(32) NULL,
                                status VARCHAR(20) NOT NULL,
                                error_message TEXT NULL,
                                latency_ms DOUBLE NULL,
                                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                            """
                        )
                        conn.exec_driver_sql(
                            """
                            INSERT INTO llm_calls
                            (dataset_key, dataset_id, difficulty, status, error_message, latency_ms, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, NOW())
                            """,
                            (
                                dataset_key_db,
                                dataset_id,
                                diff,
                                "success",
                                None,
                                llm_latency_ms,
                            ),
                        )
                    except Exception:  # noqa: BLE001
                        pass

                    source_str = "llm"

                else:
                    # 2'. 在 questions 中按 dataset_id（和可选难度）随机抽取一题。
                    base_sql = (
                        "SELECT id, title, difficulty, score, dataset_id, "
                        "COALESCE(source, 'db') AS source, "
                        "COALESCE(allow_view_answer, 0) AS allow_view_answer "
                        "FROM questions WHERE dataset_id = %s"
                    )
                    params: list[object] = [dataset_id]

                    if difficulty:
                        base_sql += " AND difficulty = %s"
                        params.append(difficulty)

                    base_sql += " ORDER BY RAND() LIMIT 1"

                    q_row = conn.exec_driver_sql(base_sql, tuple(params)).fetchone()

                    if not q_row:
                        return (
                            jsonify(
                                {
                                    "status": "error",
                                    "msg": "当前条件下暂无题目，请先在 questions 表中插入题目。",
                                }
                            ),
                            404,
                        )

                    q_id, title, diff, score, ds_id_from_q, source_str, allow_flag = q_row

        except Exception as exc:  # noqa: BLE001
            return jsonify({"status": "error", "msg": f"获取题目失败: {exc}"}), 500

        return jsonify(
            {
                "status": "success",
                "data": {
                    "id": q_id,
                    "title": title,
                    "difficulty": diff,
                    "score": score,
                    "dataset_key": dataset_key_db,
                    "source": source_str,
                    "allow_view_answer": bool(locals().get("allow_flag", 0)),
                },
            }
        )

    @app.route("/api/judge/submit", methods=["POST"])
    def api_judge_submit():
        """按题目 ID 判题并写入 records 的正式接口。

        请求 JSON 示例：
        {
          "question_id": 101,
          "user_sql": "SELECT ..."
        }
        """

        data = request.get_json(silent=True) or {}
        question_id = data.get("question_id")
        user_sql = data.get("user_sql")

        if not question_id or not user_sql:
            return (
                jsonify(
                    {
                        "status": "error",
                        "msg": "参数缺失：question_id 和 user_sql 为必填项。",
                    }
                ),
                400,
            )

        try:
            question_id_int = int(question_id)
        except (TypeError, ValueError):
            return (
                jsonify(
                    {
                        "status": "error",
                        "msg": "参数错误：question_id 必须是整数。",
                    }
                ),
                400,
            )

        # 当前登录用户 ID（未登录则为 None，后续会按 0 记匿名练习），
        # 以及返回给前端的总分（默认 None）。
        user_id = session.get("user_id")
        user_total_score: float | None = None

        try:
            with get_exam_engine().begin() as conn:
                # 1. 读取题目信息：标准 SQL、所属数据集及分值。
                q_row = conn.exec_driver_sql(
                    "SELECT standard_sql, dataset_id, score FROM questions WHERE id = %s",
                    (question_id_int,),
                ).fetchone()

                if not q_row:
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "msg": f"未找到题目: {question_id_int}",
                            }
                        ),
                        404,
                    )

                standard_sql, dataset_id, question_score = q_row

                if dataset_id is None:
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "msg": "题目未配置 dataset_id，无法判题。",
                            }
                        ),
                        500,
                    )

                # 2. 根据 dataset_id 获取物理库名。
                ds_row = conn.exec_driver_sql(
                    "SELECT db_name FROM datasets WHERE id = %s AND is_active = 1",
                    (dataset_id,),
                ).fetchone()

                if not ds_row:
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "msg": f"未找到可用数据集: dataset_id={dataset_id}。",
                            }
                        ),
                        500,
                    )

                dataset_db_name = ds_row[0]

                # 3. 调用判题逻辑并统计执行耗时。
                start_ts = perf_counter()
                judge_result = judge_sql(
                    user_sql=user_sql,
                    standard_sql=standard_sql,
                    dataset_db_name=dataset_db_name,
                )
                exec_time = perf_counter() - start_ts

                judge_status = judge_result.get("status")
                msg = judge_result.get("msg", "")

                if judge_status == "success":
                    result_str = "Pass"
                    final_score = question_score or 0
                    error_log = None
                elif judge_status == "fail":
                    result_str = "Fail"
                    final_score = 0
                    error_log = None
                else:
                    result_str = "Error"
                    final_score = 0
                    error_log = msg

                # 4. 写入提交记录：若未登录则记为 user_id = 0，仅用于练习统计。
                conn.exec_driver_sql(
                    """
                    INSERT INTO records
                    (user_id, question_id, user_sql, result, score, exec_time, error_log, dataset_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (
                        user_id or 0,
                        question_id_int,
                        user_sql,
                        result_str,
                        final_score,
                        exec_time,
                        error_log,
                        dataset_id,
                    ),
                )

                # 5. 若用户已登录且本次有得分，则累加用户总分。
                if user_id and final_score:
                    conn.exec_driver_sql(
                        "UPDATE users SET total_score = total_score + %s WHERE id = %s",
                        (final_score, user_id),
                    )
                    row_score = conn.exec_driver_sql(
                        "SELECT COALESCE(total_score, 0) FROM users WHERE id = %s",
                        (user_id,),
                    ).fetchone()
                    if row_score:
                        user_total_score = row_score[0]
        except Exception as exc:  # noqa: BLE001
            return jsonify({"status": "error", "msg": f"判题或写入记录失败: {exc}"}), 500

        return jsonify(
            {
                "status": "success",
                "data": {
                    "result": result_str,
                    "msg": msg,
                    "score": final_score,
                    "execution_time": exec_time,
                    "total_score": user_total_score,
                },
            }
        )

    @app.route("/api/question/answer", methods=["GET"])
    def api_question_answer():
        """在满足条件时返回题目的标准答案 SQL。

        条件：
        - questions.allow_view_answer = 1；
        - 当前 user_id（若未登录则为 0）在 records 中至少提交过一次该题。
        """

        qid_raw = request.args.get("question_id")
        try:
            qid = int(qid_raw)
        except (TypeError, ValueError):  # noqa: PERF203
            return (
                jsonify({"status": "error", "msg": "参数错误：question_id 必须是整数。"}),
                400,
            )

        user_id = session.get("user_id") or 0

        try:
            with get_exam_engine().connect() as conn:
                # 确保存在答案查看控制字段
                try:
                    conn.exec_driver_sql(
                        "ALTER TABLE questions ADD COLUMN allow_view_answer TINYINT(1) NOT NULL DEFAULT 0"
                    )
                except Exception:  # noqa: BLE001
                    pass

                row = conn.exec_driver_sql(
                    "SELECT standard_sql, COALESCE(allow_view_answer, 0) FROM questions WHERE id = %s",
                    (qid,),
                ).fetchone()
                if not row:
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "msg": f"未找到题目: {qid}",
                            }
                        ),
                        404,
                    )

                standard_sql, allow_flag = row
                if not allow_flag:
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "msg": "本题暂未开放查看标准答案，请联系教师或管理员设置。",
                            }
                        ),
                        403,
                    )

                cnt_row = conn.exec_driver_sql(
                    """
                    SELECT COUNT(*)
                    FROM records
                    WHERE question_id = %s AND user_id = %s
                    """,
                    (qid, user_id),
                ).fetchone()
                submitted_cnt = cnt_row[0] if cnt_row else 0
                if submitted_cnt <= 0:
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "msg": "请先提交一次你自己的解答，再查看标准答案。",
                            }
                        ),
                        403,
                    )
        except Exception as exc:  # noqa: BLE001
            return jsonify({"status": "error", "msg": f"获取标准答案失败: {exc}"}), 500

        return jsonify(
            {
                "status": "success",
                "data": {"standard_sql": standard_sql},
            }
        )

    @app.route("/api/judge/explain", methods=["POST"])
    def api_judge_explain():
        """调用大模型，对学生提交的 SQL 做中文讲解和鼓励/改进建议。"""

        data = request.get_json(silent=True) or {}
        question_id = data.get("question_id")
        user_sql = (data.get("user_sql") or "").strip()
        result = (data.get("result") or "").strip()
        judge_message = (data.get("judge_message") or "").strip()

        if not question_id or not user_sql:
            return (
                jsonify(
                    {
                        "status": "error",
                        "msg": "参数缺失：question_id 和 user_sql 为必填项。",
                    }
                ),
                400,
            )

        try:
            qid = int(question_id)
        except (TypeError, ValueError):  # noqa: PERF203
            return (
                jsonify(
                    {
                        "status": "error",
                        "msg": "参数错误：question_id 必须是整数。",
                    }
                ),
                400,
            )

        try:
            with get_exam_engine().connect() as conn:
                row = conn.exec_driver_sql(
                    """
                    SELECT
                        q.standard_sql,
                        q.dataset_id,
                        q.title,
                        d.db_name,
                        COALESCE(d.schema_desc, '') AS schema_desc
                    FROM questions q
                    LEFT JOIN datasets d ON q.dataset_id = d.id
                    WHERE q.id = %s
                    """,
                    (qid,),
                ).fetchone()
                if not row:
                    return (
                        jsonify(
                            {
                                "status": "error",
                                "msg": f"未找到题目: {qid}",
                            }
                        ),
                        404,
                    )

                standard_sql, dataset_id, title, dataset_db_name, schema_desc = row

                schema_text = schema_desc or ""
                if not schema_text and dataset_db_name:
                    try:
                        with get_dataset_engine(dataset_db_name).connect() as ds_conn:
                            rows = ds_conn.exec_driver_sql(
                                """
                                SELECT table_name, column_name, data_type
                                FROM information_schema.columns
                                WHERE table_schema = %s
                                ORDER BY table_name, ordinal_position
                                """,
                                (dataset_db_name,),
                            ).fetchall()
                    except Exception:  # noqa: BLE001
                        schema_text = ""
                    else:
                        lines: list[str] = []
                        current_table: str | None = None
                        for table_name, column_name, data_type in rows:
                            if table_name != current_table:
                                current_table = table_name
                                lines.append(f"表 {table_name}:")
                            lines.append(f"  - {column_name} ({data_type})")
                        schema_text = "\n".join(lines)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"status": "error", "msg": f"准备讲解上下文失败: {exc}"}), 500

        try:
            feedback = explain_sql_answer(
                schema_text=schema_text or "",
                title=title or "",
                standard_sql=standard_sql or "",
                user_sql=user_sql,
                result=result,
                judge_message=judge_message,
            )
        except LLMError as exc:  # noqa: BLE001
            return (
                jsonify(
                    {
                        "status": "error",
                        "msg": f"调用大模型生成讲解失败: {exc}",
                    }
                ),
                500,
            )

        return jsonify({"status": "success", "data": {"feedback": feedback}})

    return app


if __name__ == "__main__":
    # 方便本地直接运行：python app.py
    application = create_app()
    # 开发阶段打开 debug，便于查看请求日志和错误堆栈。
    application.run(host="0.0.0.0", port=5000, debug=True)

