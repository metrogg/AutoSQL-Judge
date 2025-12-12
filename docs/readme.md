
# AutoSQL-Judge · 智能 SQL 练习与判题平台

基于 **Flask + MySQL + Pandas + 大语言模型** 的 SQL 在线练习平台，支持 AI 出题、结果集级判题、自动讲解与牛客网风格的左题右码界面。

适合作为：

- 数据库课程大作业 / 课程设计
- 个人简历中的全栈 + AI 实战项目

---

## ✨ 核心特性

- **AI 出题**：
  - 基于当前数据集 Schema，由大模型动态生成 SQL 题目（题干 + 难度 + 标准答案）。
- **结果集级判题**：
  - 标准 SQL 与用户 SQL 分别执行，使用 Pandas 对结果集进行排序 + 严格比对，真正判断“结果是否一致”，而不是字符串比对。
- **牛客风界面**：
  - 左题右码布局，中间拖动条调整宽度，整体浅色扁平风格。
- **VS Code 内核编辑器**：
  - 集成 Monaco Editor（`vs-dark` 主题），支持 SQL 语法高亮、行号、自动布局。
- **多 Tab 结果区**：
  - `执行结果 / 自测输入 / 提交记录` 三个标签，搭配底部运行按钮，贴近在线刷题平台体验。
- **AI 助教讲解**：
  - 判题后一键“向 AI 寻求讲解”，生成结构化讲解与知识点梳理；悬浮聊天窗支持围绕当前题目多轮追问。
- **积分与用户系统**：
  - 登录 / 注册、积分累计，为课堂或自学提供激励机制。

---

## 🖼 界面与交互概览

> 当前前端为单页应用：`templates/index.html`（Vue 3 CDN 版本），未使用打包工具。

- **整体布局**
  - 顶部：玻璃拟态导航栏，显示当前用户与总积分。
  - 中间：左右两栏 + 中间可拖拽分隔条。

- **左侧（题目与数据）**
  - 「AI 出题对话」：输入自然语言描述（如“统计每门课的平均分并倒序”），由 LLM 生成 SQL 题目。
  - 「当前题目」：标题、难度徽章（Easy/Medium/Hard）、分值、题目来源（题库 / AI）。
  - 「数据库 Schema」：按表展示字段列表与示例数据（前若干行），辅助理解数据结构。

- **右侧（SQL 编辑与结果）**
  - 顶部工具栏：`SQL 编辑器` 标题 + 当前数据集徽章 `MySQL · student_scores`。
  - 中部：Monaco Editor 深色 SQL 编辑器。
  - 下方工具条：
    - 左侧 Tab：`执行结果 / 自测输入 / 提交记录`。
    - 右侧按钮：`运行`（提交判题）。
  - 底部内容区：
    - 执行结果：通过/失败/Error 状态条、执行耗时、结果预览表格、积分变化；支持查看标准答案与 AI 讲解。
    - 自测输入：记录自定义测试用例或期望输出的文本区。
    - 提交记录：当前会话最近提交的题目标题、时间与结果列表。

- **悬浮 AI 助教**
  - 右下角浮动按钮打开对话框，围绕当前题目与最近一次提交的判题结果进行多轮问答和知识讲解。

---

## 🧱 技术栈一览

后端：

- Python 3 + Flask
- SQLAlchemy（数据库访问）
- Pandas（SQL 结果集加载与比对）
- MySQL（系统库 + 多个靶场库）
- LLM API（DeepSeek / OpenAI，使用 Chat Completion 风格接口）

前端：

- HTML5 + 原生 CSS（Apple 风 / 牛客风定制样式）
- Bootstrap Icons（图标）
- Vue 3（CDN 版，组合式 API）
- Monaco Editor（VS Code 内核，`vs-dark` 主题）

部署与其他：

- requirements.txt 管理依赖
- Git / GitHub 作为版本管理与托管

---

## 🚀 快速开始

> 以下为开发环境启动流程，假设本地已安装 Python 3 与 MySQL。

1. **克隆项目**

```bash
git clone https://github.com/your-name/AutoSQL-Judge.git
cd AutoSQL-Judge
```

2. **创建虚拟环境并安装依赖**

```bash
python -m venv venv
venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

3. **准备数据库**

- 创建系统库 `sql_exam_sys` 与至少一个靶场库（例如 `ds_student_scores`）。
- 导入本仓库提供的建表 SQL 与示例数据（如有）。
- 在 `.env` 或 `config.py` 中配置：
  - 系统库连接字符串
  - 各靶场库连接字符串
  - LLM API Key / Base URL 等。

4. **初始化数据并启动服务**

```bash
python app.py
```

浏览器访问：`http://127.0.0.1:5000/` 即可进入学生端练习界面。

> 若首次运行失败，请优先检查数据库连接与环境变量配置是否正确。

---

## 📁 项目结构（简要）

```text
AutoSQL-Judge/
├── app.py                # Flask 入口与路由注册
├── requirements.txt      # Python 依赖
├── utils/
│   ├── db.py             # 数据库连接与 dataset 管理
│   ├── sql_judge.py      # SQL 判题核心（Pandas 结果集比对）
│   └── ai_*.py           # LLM 调用与 AI 出题/讲解逻辑
├── templates/
│   └── index.html        # 学生端主界面（Vue + Monaco + 牛客风布局）
├── static/
│   ├── css/              # 全局样式（Apple 风 + 牛客风）
│   └── js/               # 可能的前端脚本文件
└── docs/
    ├── 项目设计.md       # 系统设计与架构说明
    ├── 数据库设计-ER图与关系模式.md
    └── 技术栈简要介绍.md
```

> 以上为逻辑结构示意，实际文件名请以仓库为准。

---

## 🔍 核心模块简介

- `utils/sql_judge.py`
  - 负责将 **标准 SQL** 与 **用户 SQL** 的结果加载为 Pandas DataFrame。
  - 统一排序、重置索引后进行严格相等性比较，判断结果是否一致。
  - 返回判题状态（Pass/Fail/Error）、提示信息与执行耗时。

- `utils/db.py`
  - 封装系统库与各靶场库的连接创建逻辑。
  - 管理 `datasets` 抽象（支持未来扩展更多业务场景）。

- LLM 相关模块（如 `ai_generator / ai_explain` 等）
  - 面向两类能力：**出题** 与 **讲解**。
  - 出题：根据 Schema 生成题干 + 标准 SQL；
  - 讲解：根据题目信息、用户 SQL、判题结果与历史对话，输出多段式详细讲解。

- 前端 `templates/index.html`
  - 使用 Vue 3 组合式 API 管理所有状态（题目、Schema、SQL、判题结果、AI 信息等）。
  - 集成 Monaco Editor 并通过 `ref` 双向同步编辑器内容与 Vue 状态。
  - 实现左右分栏拖拽、底部 Tab 切换、悬浮 AI 助教拖拽等交互。

---

## 🗺 后续规划（Roadmap 简版）

- [ ] 接入更多数据集（电商订单 / 图书借阅等），丰富练习场景。
- [ ] 将提交记录持久化到数据库并在前端展示完整历史。
- [ ] 为 AI 助教增加“知识点链接”（跳转到文档或外部教程）。
- [ ] 尝试与开源 OJ 集成，将本项目作为 SQL 专项判题服务接入。

---

## 🙌 致谢与版权

- 本项目仅用于学习与教学演示，无任何商业用途。
- 部分设计灵感来自牛客网 SQL 练习界面与开源 OJ 社区。
- 欢迎提出 Issue / PR，一起完善 AI + SQL 教学体验。

