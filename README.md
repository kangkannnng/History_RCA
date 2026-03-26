# History RCA

基于历史故障案例的根因分析系统，使用多智能体架构和RAG技术进行微服务系统的故障诊断。

## 项目简介

History RCA 是一个自动化根因分析框架，通过分析日志、指标、链路追踪等可观测性数据，结合历史故障知识库，快速定位系统故障的根本原因。

## 核心特性

- **多智能体协作**：使用 Google ADK 框架实现多个专业智能体协同工作
  - Log Agent：分析应用和系统日志
  - Metric Agent：检查时序指标数据
  - Trace Agent：追踪分布式调用链路
  - RAG Agent：检索历史故障案例
  - Report Agent：生成结构化分析报告

- **历史知识库**：基于 ChromaDB 的向量数据库存储历史故障案例
- **批量处理**：支持并行处理多个故障案例

## 项目结构

```
history_rca/
├── history_rca/           # 主包
│   ├── agent.py          # 编排器智能体
│   ├── prompt.py         # 提示词模板
│   ├── sub_agents/       # 子智能体
│   │   ├── log_agent/
│   │   ├── metric_agent/
│   │   ├── trace_agent/
│   │   ├── rag_agent/
│   │   └── report_agent/
│   └── .env             # 环境变量配置
├── database_building/    # 知识库构建工具
├── input/               # 输入数据
├── output/              # 输出结果
└── main.py             # 主程序入口
```

## 安装

```bash
# 克隆仓库
git clone https://github.com/kangkannnng/History_RCA.git
cd History_RCA

# 安装依赖（推荐使用 uv）
uv sync

# 或使用 pip
pip install -e .
```

## 配置

在 `history_rca/.env` 文件中配置 API 密钥：

```bash
# OpenAI API 配置
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1

# 项目路径
PROJECT_DIR=/path/to/history_rca
```

## 使用方法

### 单个案例分析

```bash
python main.py --single <uuid>
```

### 批量处理

```bash
python main.py --batch --workers 10
```

## 知识库构建

### 1. 生成提示词

```bash
cd database_building
python generate_prompt.py
```

### 2. 调用 LLM 生成知识条目

```bash
python call_llm.py \
  --split-file ../splits/seen_train.jsonl \
  --prompts-dir prompts \
  --output-dir knowledge_base_data
```

### 3. 构建向量数据库

```bash
python build_chromadb.py \
  --input knowledge_base_data/knowledge_base.jsonl \
  --output chroma_kb
```

## 输出格式

分析结果以 JSONL 格式输出，每行包含：

```json
{
  "uuid": "case-uuid",
  "component": "identified-component",
  "reason": "root cause description"
}
```

## 依赖项

- Python >= 3.12
- google-adk >= 1.23.0
- chromadb >= 1.4.1
- openai >= 2.16.0
- pandas >= 3.0.0
- 其他依赖见 `pyproject.toml`

## License

MIT
