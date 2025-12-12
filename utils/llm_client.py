import json
from typing import Any, Dict, Optional

import requests

from config import Config


class LLMError(Exception):
    """自定义异常：封装大模型调用相关错误。"""


def _call_llm(messages: list[dict[str, str]], temperature: float = 0.3) -> str:
    """调用兼容 OpenAI Chat Completions 接口的大模型服务。

    要求在环境变量中配置：
    - LLM_API_BASE: 例如 https://api.openai.com 或自建网关地址
    - LLM_API_KEY: 访问密钥
    - LLM_MODEL: 模型名称
    """

    if not Config.LLM_API_BASE or not Config.LLM_API_KEY:
        raise LLMError("LLM API 尚未配置，请设置 LLM_API_BASE 和 LLM_API_KEY 环境变量。")

    base = Config.LLM_API_BASE.rstrip("/")
    # 兼容不同厂商的 Chat Completions 路径：
    # - OpenAI / DeepSeek 等：  {base}/v1/chat/completions
    # - 智谱 GLM-4.6：         https://open.bigmodel.cn/api/paas/v4/chat/completions
    if "open.bigmodel.cn" in base:
        url = base + "/api/paas/v4/chat/completions"
    elif "api.deepseek.com" in base:
        url = base + "/chat/completions"
    else:
        url = base + "/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {Config.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": Config.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:  # noqa: TRY003
        raise LLMError(f"请求大模型接口失败: {exc}") from exc

    data = resp.json()
    try:
        content: str = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:  # noqa: TRY003
        raise LLMError(f"大模型返回格式异常: {data}") from exc

    return content


def _strip_code_fence(text: str) -> str:
    """去掉 ```json ... ``` 代码块包装，方便做 json 解析。"""

    text = text.strip()
    if text.startswith("```"):
        # 形如 ```json\n{...}\n``` 或 ```\n{...}\n``` 的情况
        lines = text.splitlines()
        # 去掉第一行和最后一行
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return text


def generate_sql_question_from_schema(
    dataset_key: str,
    schema_text: str,
    difficulty: Optional[str] = None,
    user_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """基于给定数据集的表结构，请大模型生成一条 SQL 练习题。

    预期返回 JSON 结构：
    {
      "title": "题目标题",
      "standard_sql": "SELECT ...",
      "difficulty": "Easy|Medium|Hard",
      "score": 10
    }
    """

    sys_prompt = (
        "你是一名资深数据库课程教师，正在为学生设计基于 MySQL 的 SQL 练习题。"\
        "请根据给定的表结构生成**一条**查询题目，并给出标准答案 SQL。"\
        "题目要清晰、具体，可直接在该数据库上执行验证。"
    )

    difficulty_hint = (
        f"目标难度：{difficulty}." if difficulty else "你可以根据表结构自行选择合适的难度。"
    )

    if user_hint:
        user_requirement = (
            "学生特别希望练习的题目类型或业务场景为：" f"{user_hint}。请在题目设计中尽量满足这一需求。"
        )
    else:
        user_requirement = "你可以根据该数据集的特点，自行设计具有教学价值的业务场景。"

    user_prompt = f"""
数据集标识: {dataset_key}

下面是该数据集的表结构（仅供你理解）：
{schema_text}

请根据上述表结构生成 **1 道** SQL 查询题目，并返回 **严格的 JSON**：
{{
  "title": "自然语言描述题目，使用简体中文",
  "standard_sql": "一条可直接执行的 MySQL SELECT 语句，不要包含解释性文字",
  "difficulty": "Easy 或 Medium 或 Hard",
  "score": 10 或 20 或 30
}}

要求：
1. 仅输出 JSON，不要包含任何额外文字或代码块标记；
2. standard_sql 必须是合法的、只读的 SELECT 查询；
3. {difficulty_hint}
4. {user_requirement}
""".strip()

    content = _call_llm(
        [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )

    text = _strip_code_fence(content)

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:  # noqa: TRY003
        raise LLMError(f"解析大模型返回的 JSON 失败: {exc}; 原始内容: {text}") from exc

    if not isinstance(obj, dict):
        raise LLMError(f"大模型返回的 JSON 不是对象: {obj}")

    if not obj.get("title") or not obj.get("standard_sql"):
        raise LLMError(f"大模型返回的题目信息不完整: {obj}")

    return obj


def admin_llm_chat(message: str, extra_context: Optional[str] = None) -> str:
    message = (message or "").strip()
    if not message:
        raise LLMError("管理员消息不能为空。")

    sys_prompt = (
        "你是 AutoSQL-Judge 平台的后台管理助手，主要服务对象是教师和管理员。"
        "你需要根据提供的系统数据概览和管理员问题，给出简洁、专业、使用简体中文的回答。"
        "如果问题涉及到具体数据库数据，但当前上下文中没有提供，请明确说明你无法直接查询真实数据库，只能基于给定的信息进行推断。"
        "不要泄露任何假设的密钥或连接信息。"
    )

    if extra_context:
        user_prompt = (
            "下面是系统当前的一些数据概览（仅供参考）：\n"
            f"{extra_context}\n\n"
            "管理员的问题如下：\n"
            f"{message}\n\n"
            "请结合上述信息，用简体中文进行回答，尽量简洁。"
        )
    else:
        user_prompt = (
            "管理员的问题如下：\n"
            f"{message}\n\n"
            "请用简体中文进行回答，尽量简洁。"
        )

    content = _call_llm(
        [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )
    return content.strip()


def explain_sql_answer(
    schema_text: str,
    title: str,
    standard_sql: str,
    user_sql: str,
    result: str,
    judge_message: Optional[str] = None,
) -> str:
    """请大模型用中文讲解学生 SQL 答案的对错与改进建议。

    返回一段自然语言说明，包含：总体评价、错误分析、改进建议和涉及的知识点。
    """

    schema_text = (schema_text or "").strip()
    title = (title or "").strip()
    standard_sql = (standard_sql or "").strip()
    user_sql = (user_sql or "").strip()
    result = (result or "").strip()
    judge_message = (judge_message or "").strip()

    if not user_sql:
        raise LLMError("学生 SQL 不能为空，无法生成讲解。")

    sys_prompt = (
        "你是一名耐心的数据库课程教师，负责讲解 SQL 练习题的判题结果。"
        "请用简体中文、对学生友好的语气进行讲解，结构尽量清晰，有条理。"
    )

    user_prompt = f"""
题目描述（供你理解，不要求逐字复述）：
{title or '（题面略）'}

数据表结构（供你理解）：
{schema_text or '（表结构略，仅根据 SQL 本身判断也可以）'}

标准答案 SQL（仅供你对比用，请不要原样整体泄露给学生，只在必要时引用关键片段说明思路）：
{standard_sql or '（未提供标准答案）'}

学生提交的 SQL：
{user_sql}

判题结果：{result or '未知'}
判题提示信息与补充说明（可能为空，且可能包含错误原因、历史对话和学生的追问）：
{judge_message or '（无）'}

请你严格按照下面的结构，用简体中文给出讲解，不要输出其它无关内容：

一、总体评价
- 简要评价学生本次作答的整体情况：如果答对，请先给予肯定和鼓励；如果答错，要先肯定其尝试，再说明还有哪些地方需要改进。

二、主要问题
- 如果有错误或不完整的地方，请分条写出每一个问题：哪里错了、为什么错了（结合 SQL 逻辑说明，例如条件遗漏、JOIN 写错、GROUP BY 不正确等）。

三、改进建议
- 针对上面的每个问题，说明应该如何修改或思考，可以给出代表性的修改思路或局部 SQL 示例，但不要直接给出完整标准答案 SQL。

四、本题涉及的知识点
- 列出本题涉及的 2~5 个核心 SQL 知识点，每个知识点一行，格式为：“知识点名称：一句话解释”。

请避免长篇复述题目原文，只需围绕学生提交的 SQL、错误原因、改进方法和知识点梳理进行讲解。
""".strip()

    content = _call_llm(
        [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
    )
    return content.strip()
