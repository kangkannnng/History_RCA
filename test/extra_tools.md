# Extra Tools - 原始数据搜索工具文档

本文档介绍了为 history_rca 项目添加的三个原始数据搜索工具，用于在日志、链路追踪和指标数据中进行灵活的搜索和分析。

---

## 目录

1. [search_raw_logs - 日志搜索工具](#1-search_raw_logs---日志搜索工具)
2. [search_raw_traces - 链路追踪搜索工具](#2-search_raw_traces---链路追踪搜索工具)
3. [search_raw_metrics - 指标搜索工具](#3-search_raw_metrics---指标搜索工具)
4. [测试脚本](#4-测试脚本)

---

## 1. search_raw_logs - 日志搜索工具

### 位置
`history_rca/sub_agents/log_agent/tools.py:474-625`

### 功能描述
在原始日志数据中搜索特定服务/Pod的日志，支持正则表达式关键词匹配。

### 函数签名
```python
def search_raw_logs(
    service_name: str,
    keyword: str,
    time_range: tuple[int, int],
    max_results: int = 20
) -> dict
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `service_name` | str | 是 | 服务名称（如 "adservice"）或 pod 名称（如 "adservice-0"），支持模糊匹配 |
| `keyword` | str | 是 | 搜索关键词，**支持正则表达式**（如 "error\|exception\|fail"） |
| `time_range` | tuple[int, int] | 是 | 时间范围元组 (start_timestamp_ns, end_timestamp_ns)，纳秒级时间戳 |
| `max_results` | int | 否 | 返回的最大日志条数（默认 20） |

### 返回格式
```python
{
    "status": "success" | "error",
    "message": "状态信息",
    "logs": [
        {
            "timestamp": "2025-06-06 10:00:00.048000+00:00",
            "timestamp_ns": 1717660800048000000,
            "pod": "frontend-1",
            "node": "aiops-k8s-01",
            "message": "原始日志内容"
        },
        ...
    ],
    "total_matched": 24098,  # 总匹配数
    "returned": 10,          # 实际返回数
    "service_name": "frontend",
    "keyword": "GET|POST",
    "time_range": {
        "start": "2025-06-06 10:00:00",
        "end": "2025-06-06 10:30:00"
    }
}
```

### 使用示例

```python
from datetime import datetime
from history_rca.sub_agents.log_agent.tools import search_raw_logs

# 定义时间范围
start_time = datetime(2025, 6, 6, 10, 0, 0)
end_time = datetime(2025, 6, 6, 10, 30, 0)
start_ts = int(start_time.timestamp() * 1_000_000_000)
end_ts = int(end_time.timestamp() * 1_000_000_000)

# 示例1: 搜索包含 "error" 或 "exception" 的日志
result = search_raw_logs(
    service_name="frontend",
    keyword="error|exception",
    time_range=(start_ts, end_ts),
    max_results=20
)

# 示例2: 搜索包含 GET 请求的日志
result = search_raw_logs(
    service_name="frontend-0",
    keyword="GET.*product",
    time_range=(start_ts, end_ts),
    max_results=10
)

# 打印结果
print(f"找到 {result['total_matched']} 条匹配日志")
for log in result['logs']:
    print(f"{log['timestamp']} [{log['pod']}] {log['message']}")
```

### 核心特性
- ✅ **正则表达式支持**: 支持复杂的正则表达式搜索
- ✅ **服务/Pod 过滤**: 支持按服务名或具体 pod 名称过滤
- ✅ **时间范围过滤**: 精确到纳秒级的时间过滤
- ✅ **智能文件定位**: 根据时间范围自动定位需要读取的小时级日志文件
- ✅ **原始数据搜索**: 直接读取 `log-parquet` 目录下的原始日志文件

---

## 2. search_raw_traces - 链路追踪搜索工具

### 位置
`history_rca/sub_agents/trace_agent/tools.py:1042-1269`

### 功能描述
在原始链路追踪数据中搜索特定 trace_id、operation_name 或 attribute_key 的 spans。

### 函数签名
```python
def search_raw_traces(
    trace_id: Optional[str] = None,
    operation_name: Optional[str] = None,
    attribute_key: Optional[str] = None,
    time_range: Optional[tuple[int, int]] = None,
    max_results: int = 20
) -> dict
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `trace_id` | str | 否* | Trace ID，精确匹配 |
| `operation_name` | str | 否* | 操作名称，**支持正则表达式**（如 "GET.*product"） |
| `attribute_key` | str | 否* | 在 tags 中搜索的属性键（如 "http.status_code", "error"） |
| `time_range` | tuple[int, int] | 是 | 时间范围元组 (start_timestamp_ns, end_timestamp_ns)，纳秒级时间戳 |
| `max_results` | int | 否 | 返回的最大 span 数量（默认 20） |

*注意：`trace_id`、`operation_name`、`attribute_key` 至少需要提供一个

### 返回格式
```python
{
    "status": "success" | "error",
    "message": "状态信息",
    "traces": [
        {
            "timestamp": "2025-06-09 01:01:00.262230+00:00",
            "timestamp_ns": 1717898460262230000,
            "trace_id": "f282396c55dff7fd0fe3cd1fd725e633",
            "span_id": "e0d7ce44d84d2058",
            "operation_name": "hipstershop.ProductCatalogService/GetProduct",
            "duration": 8194,  # 纳秒
            "service_name": "productcatalogservice",
            "pod_name": "productcatalogservice-1",
            "tags": "[...]",
            "references": "[...]"
        },
        ...
    ],
    "total_matched": 31839,
    "returned": 5,
    "search_criteria": "operation_name=GET.*product",
    "time_range": {
        "start": "2025-06-09 09:00:00",
        "end": "2025-06-09 09:30:00"
    }
}
```

### 使用示例

```python
from datetime import datetime
from history_rca.sub_agents.trace_agent.tools import search_raw_traces

# 定义时间范围
start_time = datetime(2025, 6, 9, 9, 0, 0)
end_time = datetime(2025, 6, 9, 9, 30, 0)
start_ts = int(start_time.timestamp() * 1_000_000_000)
end_ts = int(end_time.timestamp() * 1_000_000_000)

# 示例1: 按 trace_id 搜索（获取完整 trace）
result = search_raw_traces(
    trace_id="f282396c55dff7fd0fe3cd1fd725e633",
    time_range=(start_ts, end_ts),
    max_results=50
)

# 示例2: 按 operation_name 搜索（支持正则）
result = search_raw_traces(
    operation_name="GET.*product",
    time_range=(start_ts, end_ts),
    max_results=10
)

# 示例3: 按 attribute_key 搜索
result = search_raw_traces(
    attribute_key="http.status_code",
    time_range=(start_ts, end_ts),
    max_results=15
)

# 示例4: 组合搜索
result = search_raw_traces(
    operation_name="POST",
    attribute_key="error",
    time_range=(start_ts, end_ts)
)

# 打印结果
print(f"找到 {result['total_matched']} 个 spans")
for trace in result['traces']:
    print(f"{trace['timestamp']} - {trace['operation_name']} (duration: {trace['duration']} ns)")
```

### 核心特性
- ✅ **按 trace_id 搜索**: 精确匹配特定 trace ID，返回该 trace 的所有 spans
- ✅ **按 operation_name 搜索**: 支持正则表达式匹配操作名称
- ✅ **按 attribute_key 搜索**: 在 tags 中搜索特定属性键
- ✅ **组合搜索**: 支持多个条件同时使用（AND 逻辑）
- ✅ **原始数据搜索**: 直接读取 `trace-parquet` 目录下的原始 trace 文件

---

## 3. search_raw_metrics - 指标搜索工具

### 位置
`history_rca/sub_agents/metric_agent/tools.py:1661-1905`

### 功能描述
在原始指标数据中搜索特定 metric_name 和可选的 service_name，支持 APM 和 Infra 两类指标。

### 函数签名
```python
def search_raw_metrics(
    metric_name: str,
    service_name: Optional[str] = None,
    time_range: Optional[Tuple[int, int]] = None,
    max_results: int = 100
) -> dict
```

### 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `metric_name` | str | 是 | 指标名称（如 "pod_cpu_usage", "rrt", "error_ratio"） |
| `service_name` | str | 否 | 服务名称或 pod 名称过滤（如 "adservice", "frontend-0"） |
| `time_range` | tuple[int, int] | 是 | 时间范围元组 (start_timestamp_ns, end_timestamp_ns)，纳秒级时间戳 |
| `max_results` | int | 否 | 返回的最大数据点数量（默认 100） |

### 支持的指标类型

#### APM 指标（应用性能监控）
存储位置：`data/processed/{date}/metric-parquet/apm/pod/`

| 指标名称 | 说明 |
|---------|------|
| `error_ratio` | 错误率 |
| `rrt` | 平均响应时间 |
| `rrt_max` | 最大响应时间 |
| `client_error_ratio` | 客户端错误率 |
| `server_error_ratio` | 服务端错误率 |
| `request` | 请求数 |
| `response` | 响应数 |
| `timeout` | 超时数 |
| `client_error` | 客户端错误数 |
| `server_error` | 服务端错误数 |
| `error` | 总错误数 |

#### Infra 指标（基础设施监控）
存储位置：`data/processed/{date}/metric-parquet/infra/infra_pod/`

| 指标名称 | 说明 |
|---------|------|
| `pod_cpu_usage` | Pod CPU 使用率 |
| `pod_memory_working_set_bytes` | Pod 内存使用量（字节） |
| `pod_network_receive_bytes` | Pod 网络接收字节数 |
| `pod_network_transmit_bytes` | Pod 网络发送字节数 |
| `pod_network_receive_packets` | Pod 网络接收包数 |
| `pod_network_transmit_packets` | Pod 网络发送包数 |
| `pod_fs_reads_bytes` | Pod 文件系统读取字节数 |
| `pod_fs_writes_bytes` | Pod 文件系统写入字节数 |
| `pod_processes` | Pod 进程数 |

### 返回格式

#### APM 指标返回格式
```python
{
    "status": "success",
    "message": "Found 31 matching data points in original data, returning 10",
    "metrics": [
        {
            "timestamp": "2025-06-06 02:00:00+00:00",
            "timestamp_ns": 1749139200000000000,
            "pod_name": "adservice-0",
            "metric_name": "error_ratio",
            "metric_value": 0.0,
            "object_type": "pod"
        },
        ...
    ],
    "total_matched": 31,
    "returned": 10,
    "metric_name": "error_ratio",
    "metric_type": "apm",
    "service_name": "adservice",
    "time_range": {
        "start": "2025-06-06 10:00:00",
        "end": "2025-06-06 10:30:00"
    }
}
```

#### Infra 指标返回格式
```python
{
    "status": "success",
    "message": "Found 93 matching data points in original data, returning 10",
    "metrics": [
        {
            "timestamp": "2025-06-06 02:00:00+00:00",
            "timestamp_ns": 1749139200000000000,
            "pod_name": "frontend-1",
            "node_name": "aiops-k8s-01",
            "metric_name": "pod_cpu_usage",
            "metric_value": 0.03,
            "namespace": "hipstershop"
        },
        ...
    ],
    "total_matched": 93,
    "returned": 10,
    "metric_name": "pod_cpu_usage",
    "metric_type": "infra",
    "service_name": "frontend",
    "time_range": {
        "start": "2025-06-06 10:00:00",
        "end": "2025-06-06 10:30:00"
    }
}
```

### 使用示例

```python
from datetime import datetime
from history_rca.sub_agents.metric_agent.tools import search_raw_metrics

# 定义时间范围
start_time = datetime(2025, 6, 6, 10, 0, 0)
end_time = datetime(2025, 6, 6, 10, 30, 0)
start_ts = int(start_time.timestamp() * 1_000_000_000)
end_ts = int(end_time.timestamp() * 1_000_000_000)

# 示例1: 搜索特定服务的错误率（APM 指标）
result = search_raw_metrics(
    metric_name="error_ratio",
    service_name="adservice",
    time_range=(start_ts, end_ts),
    max_results=50
)

# 示例2: 搜索特定服务的 CPU 使用率（Infra 指标）
result = search_raw_metrics(
    metric_name="pod_cpu_usage",
    service_name="frontend",
    time_range=(start_ts, end_ts)
)

# 示例3: 搜索所有服务的响应时间
result = search_raw_metrics(
    metric_name="rrt",
    time_range=(start_ts, end_ts),
    max_results=100
)

# 示例4: 搜索内存使用量
result = search_raw_metrics(
    metric_name="pod_memory_working_set_bytes",
    service_name="cartservice",
    time_range=(start_ts, end_ts)
)

# 打印结果
print(f"找到 {result['total_matched']} 个数据点")
print(f"指标类型: {result['metric_type']}")
for metric in result['metrics'][:5]:
    print(f"{metric['timestamp']} - {metric['pod_name']}: {metric['metric_value']}")
```

### 核心特性
- ✅ **自动识别指标类型**: 自动判断是 APM 指标还是 Infra 指标
- ✅ **按 metric_name 搜索**: 支持 APM 和 Infra 两类指标
- ✅ **按 service_name 过滤**: 可选的服务名或 pod 名过滤
- ✅ **时间范围过滤**: 精确到纳秒级的时间过滤
- ✅ **原始数据搜索**: 直接读取 `metric-parquet` 目录下的原始指标文件

---

## 4. 测试脚本

### 日志搜索测试
```bash
python test_search_logs.py
```
测试文件：`test_search_logs.py`

### 链路追踪搜索测试
```bash
python test_search_traces.py
```
测试文件：`test_search_traces.py`

### 指标搜索测试
```bash
python test_search_metrics.py
```
测试文件：`test_search_metrics.py`

---

## 5. 常见使用场景

### 场景1: 故障排查 - 查找错误日志
```python
# 在故障时间段内查找包含错误的日志
result = search_raw_logs(
    service_name="frontend",
    keyword="error|exception|fail",
    time_range=(fault_start_ts, fault_end_ts),
    max_results=50
)
```

### 场景2: 性能分析 - 查找慢请求
```python
# 查找响应时间异常的 trace
result = search_raw_traces(
    operation_name="GET.*",
    attribute_key="http.status_code",
    time_range=(start_ts, end_ts),
    max_results=20
)

# 过滤出 duration > 1000ms 的 spans
slow_traces = [t for t in result['traces'] if t['duration'] > 1000000000]
```

### 场景3: 资源监控 - 查看 CPU/内存趋势
```python
# 查看某个服务的 CPU 使用率趋势
result = search_raw_metrics(
    metric_name="pod_cpu_usage",
    service_name="cartservice",
    time_range=(start_ts, end_ts),
    max_results=200
)

# 计算平均值
avg_cpu = sum([m['metric_value'] for m in result['metrics']]) / len(result['metrics'])
print(f"平均 CPU 使用率: {avg_cpu:.2%}")
```

### 场景4: 完整链路追踪 - 根据 trace_id 查看完整调用链
```python
# 先从日志中找到 trace_id
log_result = search_raw_logs(
    service_name="frontend",
    keyword="trace_id.*abc123",
    time_range=(start_ts, end_ts),
    max_results=1
)

# 然后查找该 trace 的所有 spans
trace_result = search_raw_traces(
    trace_id="abc123",
    time_range=(start_ts, end_ts),
    max_results=100
)

# 按时间顺序查看调用链
for span in trace_result['traces']:
    print(f"{span['operation_name']} - {span['duration']}ns")
```

---

## 6. 注意事项

1. **时间戳格式**: 所有时间戳都是纳秒级（nanoseconds），需要使用 `int(timestamp * 1_000_000_000)` 转换

2. **正则表达式**: `search_raw_logs` 和 `search_raw_traces` 的 `keyword`/`operation_name` 参数支持正则表达式，注意转义特殊字符

3. **结果限制**: 使用 `max_results` 参数控制返回数量，避免数据过载

4. **跨天搜索**: 当前实现仅支持单日搜索，如果时间范围跨天，只会搜索起始日期的数据

5. **文件命名**:
   - 日志文件: `log_filebeat-server_{date}_{hour:02d}-00-00.parquet`
   - Trace 文件: `trace_jaeger-span_{date}_{hour:02d}-00-00.parquet`
   - Metric 文件: `infra_pod_{metric_name}_{date}.parquet` 或 `pod_{pod_name}_{date}.parquet`

6. **性能考虑**: 搜索大时间范围的数据可能较慢，建议缩小时间范围或增加过滤条件

---

## 7. 错误处理

所有函数都返回统一的错误格式：

```python
{
    "status": "error",
    "message": "错误描述信息",
    "logs/traces/metrics": [],
    "total_matched": 0,
    "returned": 0
}
```

常见错误：
- `"metric_name parameter is required"` - 缺少必填参数
- `"time_range parameter is required"` - 缺少时间范围
- `"Invalid regex pattern"` - 正则表达式语法错误
- `"Directory not found"` - 数据目录不存在
- `"No data found"` - 指定条件下没有数据

---

## 8. 版本信息

- **创建日期**: 2026-01-30
- **Python 版本**: 3.12+
- **依赖库**: pandas, pyarrow (用于读取 parquet 文件)

---

## 9. 联系方式

如有问题或建议，请查看项目 README 或提交 Issue。
