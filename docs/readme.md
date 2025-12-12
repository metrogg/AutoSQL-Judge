# 项目实战指南：基于大模型的智能SQL判题系统

**项目代号：** AutoSQL-Judge
**开发者：** [你的名字]
**预计工期：** 2周
**项目定位：** 数据库课程综合实验 / 个人简历全栈AI实战项目

------

## 1. 核心需求与功能架构

### 1.1 核心价值

解决传统SQL题库死板、题目有限的问题。利用AI基于特定的数据库结构（Schema）动态生成题目，并自动通过执行结果对比来判分，而非简单的文本比对。

### 1.2 功能模块

1. **题目生成引擎 (AI-Powered)**：调用 LLM API 基于数据库 Schema 动态生成题目。
2. **判题核心 (The Judge)**：
   - **沙箱执行**：分别运行"标准答案"和"用户提交的答案"。
   - **逻辑比对**：使用 Pandas 库比对两个结果集（DataFrame）的数据是否一致。
3. **用户系统**：注册登录、积分累计、排行榜展示。
4. **用户界面 (Web UI)**：
   - 左侧：数据库表结构展示、题目描述。
   - 右侧：SQL 代码编辑器、提交按钮、结果反馈区。

------

## 2. 技术栈选型 (Tech Stack)

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| **开发环境** | Windows 10/11 | 本地开发环境 |
| **数据库服务** | phpStudy (MySQL 5.7/8.0) | 符合实验要求 |
| **后端框架** | Python 3.9+ + Flask | 轻量级，适合快速开发 |
| **数据库交互** | PyMySQL + SQLAlchemy + Pandas | 驱动 + ORM + 数据处理 |
| **AI模型** | DeepSeek V3 API / OpenAI | 推荐 DeepSeek，性价比高 |
| **前端** | HTML5 + Bootstrap 5 + Vue 3 | CDN引入，无需构建工具 |
| **版本控制** | Git + GitHub | 代码托管与版本管理 |

## 3. 数据库详细设计 (Database Schema)

请在 phpMyAdmin 中创建 **1 个系统库 + 多个靶场库**：

### 3.1 ds_student_scores (靶场库 - 用户只读，默认示例)

用途：存放学生成绩场景的业务数据，供用户查询练习。

- **students** (学生表): `student_id`, `name`, `gender`, `age`, `major`
- **courses** (课程表): `course_id`, `name`, `credits`
- **scores** (成绩表): `student_id`, `course_id`, `score` (联合主键)

> 进阶：你可以按文档扩展再创建 `ds_ecommerce_orders`（电商订单场景）、`ds_library_loans`（图书借阅场景）等更多靶场库。

### 3.2 sql_exam_sys (系统库 - 核心业务)

用途：存放系统运行所需的数据。

- **users** (用户表): `id`, `username`, `password_hash`, `total_score`, `created_at`
- **questions** (题目缓存表): `id`, `title`, `standard_sql`, `difficulty`, `score`, `created_at`
- **records** (做题记录表): `id`, `user_id`, `question_id`, `user_sql`, `result`, `score`, `exec_time`, `error_log`, `created_at`

## 4. GitHub 项目初始化指南

这是你开始写代码前的第一步。

## 5. 开发路线图 (Roadmap)

按这个顺序做，每天一个里程碑。

### **Phase 1: 基础设施搭建 (Day 1-2)**

跑通 Hello World，连接数据库。

1. 启动 phpStudy，创建好 `sql_exam_sys` 和 `ds_student_scores` 两个库（可选再建 `ds_ecommerce_orders` / `ds_library_loans`），并填入一些测试数据。
2. 创建 Python 虚拟环境：
   ```bash
   python -m venv venv
   # Windows激活:
   venv\Scripts\activate
   ```
3. 安装依赖包：
   ```bash
   pip install flask pymysql sqlalchemy pandas openai python-dotenv
   ```
4. 编写 `config.py` (存放数据库配置) 和 `app.py` (Flask启动文件)。
5. 测试：运行 `app.py`，浏览器访问 http://127.0.0.1:5000 显示成功。

### **Phase 2: AI 出题与逻辑实现 (Day 3-5)**

**目标**：后端能让AI生成题目，能执行SQL。

1. **AI 模块** (`ai_engine.py`)：
   - 编写函数 `generate_question(schema_text)`
   - 构造 Prompt："你是一个SQL专家，基于以下表结构...生成一道查询题..."
2. **判题模块** (`judge.py`)：
   - 编写函数 `execute_sql(sql)`：连接 `ds_student_scores`（或其他 `ds_*` 靶场库）执行查询，返回 Pandas DataFrame
   - 编写函数 `check_answer(user_sql, standard_sql)`：比较两个 DataFrame 是否相等
3. **API 接口开发**：
   - `GET /api/new_question`：返回题目
   - `POST /api/submit`：接收用户SQL，返回对错

### **Phase 3: 前端开发 (Day 6-8)**

界面能看，能交互。

1. 创建 `templates/index.html`
2. 引入 Bootstrap (CSS) 和 Vue 3 (JS)
3. 编写左侧栏：用 Vue 的 `v-for` 渲染表结构
4. 编写中间栏：题目描述区域
5. 编写右侧栏：输入框 (`<textarea>`) 和"运行"按钮
6. 联调：点击按钮 -> 发送 fetch 请求 -> 显示后端返回的结果

### **Phase 4: 优化与文档 (Day 9-10)**

1. **安全优化**：在后端加正则判断，禁止 DROP, DELETE 等危险词
2. **测试**：自己做几遍题，确保报错信息能正常显示
3. **PPT与报告**：截图核心代码，画出 E-R 图，生成演示视频
4. **Git 提交**：
   ```bash
   git add .
   git commit -m "Finish v1.0"
   git push
   ```

------

## 6. 关键代码片段 (Cheat Sheet)

### 6.1 目录结构推荐

```markdown
sql-ai-judge/
├── app.py              # Flask 主入口
├── config.py           # 配置（不要上传GitHub）
├── requirements.txt    # 依赖列表
├── utils/
│   ├── ai_generator.py # AI 调用逻辑
│   └── sql_judge.py    # 判题逻辑
├── static/             # 存放 css, js
└── templates/
    └── index.html      # 前端页面
```

### 6.2 AI Prompt 模板 (Python)

```python
# utils/ai_generator.py
SYSTEM_PROMPT = """你是一个数据库专家。请根据提供的 Schema（表结构），生成一道 SQL 查询练习题。
输出必须是严格的 JSON 格式，包含以下字段：
1. "question": 题目的自然语言描述（中文）。
2. "difficulty": 难度（简单/中等）。
3. "sql": 标准答案 SQL 语句（确保在 MySQL 下可执行）。

Schema 如下：
{schema_str}
"""
```

### 6.3 判题核心逻辑 (Pandas)

```python
# utils/sql_judge.py
import pandas as pd
from sqlalchemy import create_engine

# 创建只读连接（示例：连接学生成绩靶场库 ds_student_scores）
db_url = "mysql+pymysql://root:root@localhost/ds_student_scores"
engine = create_engine(db_url)

def judge_sql(user_sql, standard_sql):
    try:
        # 执行标准答案
        df_std = pd.read_sql(standard_sql, engine)
        # 执行用户答案
        df_user = pd.read_sql(user_sql, engine)
        
        # 核心比对逻辑：忽略行顺序，重置索引后比对
        # 1. 排序
        df_std = df_std.sort_values(by=df_std.columns.tolist()).reset_index(drop=True)
        df_user = df_user.sort_values(by=df_user.columns.tolist()).reset_index(drop=True)
        
        # 2. 比对
        if df_std.equals(df_user):
            return {"status": "success", "msg": "恭喜！答案正确！"}
        else:
            return {"status": "fail", "msg": "结果不一致，请检查逻辑。"}
            
    except Exception as e:
        return {"status": "error", "msg": str(e)}
```

------

## 7. 学习资源清单

在开发过程中遇到不懂的，按这个清单去搜：

- **Flask 基础**：搜 "Flask 快速上手 廖雪峰" 或 B站 "Flask 教程"
- **前端交互**：搜 "Vue3 CDN 简单教程" (不用学脚手架，学怎么直接在HTML里写Vue)
- **Git 命令**：搜 "Git 常用命令速查表"
- **AI API**：去 DeepSeek 或 OpenAI 官网看 "API Documentation" -> "Chat Completions"

------

**建议：**
现在，你可以先去 **GitHub** 建仓库，然后在本地建好文件夹，把 requirements.txt 和 readme.md 建好，这就是今天的第一步！