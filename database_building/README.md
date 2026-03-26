# AIOps 故障诊断知识库构建系统

从历史RCA案例中自动提炼可执行的故障诊断规则，构建结构化的AIOps知识库。

## 🌟 核心特性

### 智能知识提取
- **多模态证据融合** - 整合 Trace、Log、Metric 三种数据源
- **推理链重构** - 基于Ground Truth在原始数据中重建正确的诊断路径
- **规则标准化** - 生成结构化的故障诊断规则（symptom → reasoning → checks）
- **质量验证** - 自动验证输出格式和必需字段完整性

### 数据集管理
- **训练/测试分割** - 支持seen_train、seen_test、unseen_test三个数据集
- **批量并行处理** - 异步API调用，支持进度条和自动重试
- **完整性保证** - 不截断输入数据，充分利用128k上下文窗口

## 🚀 快速开始

### 安装依赖

```bash
# 安装必需的包
pip install openai tqdm
```

### 完整流程

#### 1. 生成Prompts

```bash
# 为所有cases生成prompts
python generate_knowledge_base_prompts.py

# 查看生成的prompts
ls knowledge_base_prompts/
```

#### 2. 调用LLM生成知识库

```bash
# 处理训练集（默认）
python call_llm.py --retry-failed --max-concurrent 10

# 处理seen测试集
python call_llm.py \
  --split-file output/splits/seen_test_uuids.txt \
  --output-dir knowledge_base_data/test \
  --retry-failed

# 处理unseen测试集
python call_llm.py \
  --split-file output/splits/unseen_test_uuids.txt \
  --output-dir knowledge_base_data/unseen \
  --retry-failed

# 处理特定cases
python call_llm.py --cases bc9db995-235 3c7d0c09-484
```

## 📊 输入数据格式

### Ground Truth (output/groundtruth.jsonl)

```json
{
  "uuid": "b1ab098d-83",
  "instance": "aiops-k8s-06",
  "key_observations": [
    {"type": "metric", "keyword": ["node_memory_usage_rate", "node_memory_MemAvailable_bytes"]}
  ],
  "key_metrics": ["node_memory_usage_rate"],
  "fault_description": ["node memory exhaustion", "node memory saturation"]
}
```

### 历史结论 (output/result.jsonl)

```json
{
  "uuid": "b1ab098d-83",
  "component": "currencyservice-0",
  "reason": "rrt_max P99变化率150.44%导致尾部延迟异常",
  "reasoning_trace": [
    {"step": 1, "action": "LoadMetrics", "observation": "..."},
    {"step": 2, "action": "TraceAnalysis", "observation": "..."}
  ]
}
```

### 完整日志 (logs/{uuid}/run.log)

包含完整的诊断过程，包括：
- Trace分析结果
- Log搜索结果
- Metric异常数据
- 多智能体推理过程

## 📁 输出格式

### 知识库条目 (knowledge_base_data/{uuid}.json)

```json
{
  "uuid": "b1ab098d-83",
  "fault_type": "node_memory_stress",
  "symptom_vector": "High memory usage rate on node, multiple pod performance degradation",
  "expert_knowledge": {
    "root_cause_desc": "节点内存使用率异常飙升，导致文件系统资源耗尽",
    "reasoning_chain": [
      "Step 1: 观察到node_filesystem_usage_rate从53.72%激增至80.74%",
      "Step 2: 分析调用链发现该节点上的服务延迟严重增加",
      "Step 3: 日志中无应用错误，确认为基础设施故障"
    ],
    "critical_checks": [
      {
        "modality": "Metric",
        "target": "node_filesystem_usage_rate",
        "expected_pattern": "Sudden increase >30% change rate",
        "instruction": "筛选故障期间node_filesystem_usage_rate变化率最高的节点"
      },
      {
        "modality": "Trace",
        "target": "pods on suspect node",
        "expected_pattern": "Severe latency degradation (5x+ increase)",
        "instruction": "检查问题节点上所有Pod的调用链延迟"
      },
      {
        "modality": "Log",
        "target": "error logs related to filesystem/disk",
        "expected_pattern": "Absence of application errors",
        "instruction": "确认无应用层错误，支持基础设施故障假设"
      }
    ]
  }
}
```

### 合并的知识库 (knowledge_base_data/knowledge_base.jsonl)

JSONL格式，每行一个完整的知识库条目，便于：
- 向量数据库导入
- 批量处理
- 增量更新

### 验证报告 (knowledge_base_data/validation_report.json)

```json
{
  "bc9db995-235": {
    "uuid": "bc9db995-235",
    "status": "success",
    "valid": true,
    "issues": [],
    "entry": {...}
  },
  "271c6b09-108": {
    "uuid": "271c6b09-108",
    "status": "needs_review",
    "valid": false,
    "issues": ["Missing required field: expert_knowledge"]
  }
}
```

## 🔧 命令行参数

### generate_knowledge_base_prompts.py

```bash
--gt-file           Ground Truth文件路径（默认: output/groundtruth.jsonl）
--result-file       历史结论文件路径（默认: output/result.jsonl）
--logs-dir          日志目录路径（默认: logs）
--output-dir        输出目录（默认: knowledge_base_prompts）
--cases             指定处理的case UUIDs
```

### call_llm.py

```bash
--prompts-dir       Prompt文件目录（默认: knowledge_base_prompts）
--output-dir        输出目录（默认: knowledge_base_data）
--split-file        数据集分割文件（默认: output/splits/seen_train_uuids.txt）
--cases             指定处理的case UUIDs
--api-key           DeepSeek API密钥
--base-url          API Base URL
--max-concurrent    最大并发数（默认: 10）
--retry-failed      自动重试失败的cases
--max-retries       最大重试次数（默认: 2）
```

## 📈 数据集统计

### 数据分割

| 数据集 | 数量 | 文件路径 |
|--------|------|----------|
| 训练集 | 248 | output/splits/seen_train_uuids.txt |
| Seen测试集 | 117 | output/splits/seen_test_uuids.txt |
| Unseen测试集 | 35 | output/splits/unseen_test_uuids.txt |
| **总计** | **400** | |

### 处理结果示例

```
Total cases: 248
✓ Valid entries: 246
⚠ Needs review: 2
✗ Errors: 0

Success rate: 99.2%
```

## 🔍 质量验证

### 自动验证项

1. **必需字段检查**
   - uuid, fault_type, symptom_vector, expert_knowledge

2. **expert_knowledge子字段**
   - root_cause_desc（根因描述）
   - reasoning_chain（推理链，至少2步）
   - critical_checks（关键检查项，非空列表）

3. **critical_checks验证**
   - modality必须是 "Trace"、"Log" 或 "Metric"
   - 必须包含 target、expected_pattern、instruction

4. **UUID一致性**
   - 返回的UUID与请求的UUID匹配

### 查看验证结果

```bash
# 查看验证报告
cat knowledge_base_data/validation_report.json | jq '.'

# 统计各状态数量
cat knowledge_base_data/validation_report.json | jq -r '.[] | .status' | sort | uniq -c

# 查看需要review的cases
cat knowledge_base_data/validation_report.json | jq 'to_entries[] | select(.value.valid == false)'
```

## 🎯 使用场景

### 1. RAG检索增强

将知识库导入向量数据库：

```python
import chromadb
import json

client = chromadb.Client()
collection = client.create_collection("fault_diagnosis_kb")

with open("knowledge_base_data/knowledge_base.jsonl") as f:
    for line in f:
        entry = json.loads(line)
        collection.add(
            ids=[entry['uuid']],
            documents=[entry['expert_knowledge']['root_cause_desc']],
            metadatas=[{
                'fault_type': entry['fault_type'],
                'symptom': entry['symptom_vector']
            }]
        )
```

### 2. 规则引擎

将critical_checks转换为可执行规则：

```python
def execute_checks(entry, runtime_data):
    for check in entry['expert_knowledge']['critical_checks']:
        if check['modality'] == 'Metric':
            # 执行指标检查
            result = check_metric(check['target'], check['expected_pattern'])
        elif check['modality'] == 'Log':
            # 执行日志检查
            result = check_log(check['target'], check['expected_pattern'])
        elif check['modality'] == 'Trace':
            # 执行调用链检查
            result = check_trace(check['target'], check['expected_pattern'])
```

### 3. 训练数据生成

使用reasoning_chain作为训练数据：

```python
# 生成问答对
for entry in knowledge_base:
    question = f"如何诊断{entry['symptom_vector']}?"
    answer = "\n".join(entry['expert_knowledge']['reasoning_chain'])
    training_data.append({'question': question, 'answer': answer})
```

## 🛠️ 故障排查

### 问题：Prompt文件未生成

```bash
# 检查输入文件是否存在
ls output/groundtruth.jsonl output/result.jsonl

# 重新生成prompts
python generate_knowledge_base_prompts.py
```

### 问题：API调用失败

```bash
# 检查网络连接
curl -I https://api.huiyan-ai.cn

# 降低并发数
python call_llm.py --max-concurrent 5
```

### 问题：JSON解析失败

查看原始响应：
```bash
cat knowledge_base_data/raw_responses/{uuid}.txt
```

### 问题：需要重新处理特定cases

```bash
# 重新处理失败的cases
python call_llm.py --cases 271c6b09-108 9a257bd5-150 --retry-failed
```

### 问题：合并的JSONL文件不完整

```bash
# 重新生成knowledge_base.jsonl
python3 << 'EOF'
import json
from pathlib import Path

kb_dir = Path("knowledge_base_data")
json_files = [f for f in kb_dir.glob("*.json") if f.name != "validation_report.json"]

with open(kb_dir / "knowledge_base.jsonl", 'w', encoding='utf-8') as out:
    for json_file in sorted(json_files):
        with open(json_file, 'r', encoding='utf-8') as f:
            entry = json.load(f)
            out.write(json.dumps(entry, ensure_ascii=False) + '\n')
EOF
```

## 📚 技术细节

### Prompt设计原则

1. **完整上下文** - 提供Ground Truth、历史结论、完整日志（不截断）
2. **三模态约束** - 严格限制证据来源为Trace/Log/Metric
3. **推理导向** - 要求"通过观察数据推导"而非"根据GT"
4. **结构化输出** - 强制JSON格式，便于自动化处理

### 数据流

```
1. 数据准备
   ├─ output/groundtruth.jsonl (标准答案)
   ├─ output/result.jsonl (历史结论)
   └─ logs/{uuid}/run.log (完整诊断过程)

2. Prompt生成
   ├─ 提取GT关键字段（故障组件、特征、原因、描述）
   ├─ 提取历史结论（用于判卷）
   └─ 加载完整日志（不截断，利用128k上下文）

3. LLM调用
   ├─ 异步并行处理（控制并发数）
   ├─ 自动重试失败cases
   └─ 实时进度条显示

4. 结果验证
   ├─ JSON格式提取
   ├─ 必需字段验证
   ├─ modality合法性检查
   └─ 生成验证报告

5. 输出保存
   ├─ 独立JSON文件（每个case）
   ├─ 合并JSONL文件（便于批处理）
   ├─ 原始响应（用于调试）
   └─ 验证报告（质量追踪）
```

### 性能优化

- **异步并发** - 使用asyncio并行调用API
- **进度追踪** - tqdm实时显示处理进度
- **自动重试** - 失败cases自动重试，提高成功率
- **增量处理** - 支持指定特定cases，避免重复处理

## 📊 统计分析

```bash
# 总条目数
wc -l knowledge_base_data/knowledge_base.jsonl

# 按fault_type统计
cat knowledge_base_data/knowledge_base.jsonl | jq -r '.fault_type' | sort | uniq -c

# 按modality统计critical_checks
cat knowledge_base_data/knowledge_base.jsonl | \
  jq -r '.expert_knowledge.critical_checks[].modality' | sort | uniq -c

# 平均reasoning_chain步数
cat knowledge_base_data/knowledge_base.jsonl | \
  jq '.expert_knowledge.reasoning_chain | length' | \
  awk '{sum+=$1; count++} END {print sum/count}'

# 查看特定UUID
cat knowledge_base_data/knowledge_base.jsonl | jq 'select(.uuid == "b1ab098d-83")'
```

## 🤝 贡献

欢迎提交Issue和Pull Request！

## 📄 许可证

MIT License

---

**项目状态：** ✅ 生产就绪

**最后更新：** 2026-01-30

**模型版本：** DeepSeek v3.2 (128k context)
