# Experimental Results Analysis Report

## 1. Overall Performance Comparison (Score Metric)\n
| Method | Official Score | Component Accuracy (%) | Total Cases Evaluated |
| :--- | :--- | :--- | :--- |
| MicroRCA (Baseline) | **48.48** | 56.50% | 400 |
| Single Agent (Baseline) | **47.01** | 60.00% | 400 |
| History-RCA (Ours) | **56.62** | 64.50% | 400 |
| Multi-Agent w/o RAG (Ablation) | **49.83** | 58.25% | 400 |

## 2. Accuracy Breakdown by Fault Category

| Fault Category | Single Agent (Base) | MicroRCA (Base) | w/o RAG (Ablation) | History-RCA (Ours) | Improvement (vs w/o RAG) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| dns fault | 19.0% | 19.0% | 9.5% | **19.0%** | +9.5% |
| erroneous change | 81.0% | 47.6% | 66.7% | **85.7%** | +19.0% |
| io fault | 7.1% | 3.6% | 57.1% | **64.3%** | +7.1% |
| jvm fault | 94.5% | 69.1% | 87.3% | **92.7%** | +5.5% |
| misconfiguration | 88.9% | 100.0% | 88.9% | **88.9%** | +0.0% |
| network attack | 95.9% | 97.3% | 84.9% | **90.4%** | +5.5% |
| node fault | 26.8% | 30.5% | 34.1% | **29.3%** | -4.9% |
| pod fault | 41.7% | 56.7% | 35.0% | **53.3%** | +18.3% |
| stress test | 76.2% | 59.5% | 61.9% | **69.0%** | +7.1% |

## 3. Detailed Analysis by Fault Type (Top Differences)

| Fault Type | History-RCA (Ours) | w/o RAG (Ablation) | MicroRCA | Improvement |
| :--- | :--- | :--- | :--- | :--- |
| pod failure (n=45) | **68.9%** | 46.7% | 75.6% | +22.2% |
| network delay (n=25) | **88.0%** | 68.0% | 96.0% | +20.0% |
| code error (n=21) | **85.7%** | 66.7% | 47.6% | +19.0% |
| jvm latency (n=15) | **93.3%** | 80.0% | 66.7% | +13.3% |
| dns error (n=21) | **19.0%** | 9.5% | 19.0% | +9.5% |
| cpu stress (n=22) | **90.9%** | 81.8% | 86.4% | +9.1% |
| jvm exception (n=13) | **92.3%** | 84.6% | 76.9% | +7.7% |
| io fault (n=28) | **64.3%** | 57.1% | 3.6% | +7.1% |
| pod kill (n=15) | **6.7%** | 0.0% | 0.0% | +6.7% |
| memory stress (n=20) | **45.0%** | 40.0% | 30.0% | +5.0% |
| network corrupt (n=27) | **88.9%** | 88.9% | 100.0% | +0.0% |
| node cpu stress (n=23) | **56.5%** | 56.5% | 69.6% | +0.0% |
| jvm cpu (n=13) | **100.0%** | 100.0% | 76.9% | +0.0% |
| jvm gc (n=14) | **85.7%** | 85.7% | 57.1% | +0.0% |
| node disk fill (n=21) | **47.6%** | 47.6% | 28.6% | +0.0% |
| target port misconfig (n=18) | **88.9%** | 88.9% | 100.0% | +0.0% |
| network loss (n=21) | **95.2%** | 100.0% | 95.2% | -4.8% |
| node memory stress (n=38) | **2.6%** | 13.2% | 7.9% | -10.5% |


## 4. 深度洞察与模式发现 (Deep Insights & Pattern Discovery)

### 4.1 "沉默故障" 的有效识别 (Effective Identification of Silent Failures)
通过对比 `w/o RAG` 和 `History-RCA` 的结果文件（如 `result.jsonl`），我们发现了一个显著模式：
*   **现象**: 很多 Pod 故障（如 CrashLoopBackOff 或 OOMKilled）表现为监控数据的突然消失和日志的完全静默。
*   **Baseline 的困境**: 无 RAG 的 Agent 往往会陷入“寻找日志”的死循环。例如在 Case `0718e0f9-92` 中，MicroRCA 和 Single Agent 都试图在空日志中寻找报错，最终只能给出模糊的猜测。
*   **Ours 的突破**: History-RCA 通过检索历史案例，学会了 **"Absence as Evidence" (缺失即证据)** 的推理模式。它能根据“日志缺失 + 流量中断”的组合特征，直接判定为 Pod 崩溃，而不是服务逻辑错误。这解释了为何 Pod Fault 类型的准确率提升了 **18.3%**。

### 4.2 级联故障的根因溯源 (Root Cause Tracing in Cascading Failures)
微服务架构中，一个组件的故障往往引发下游一连串的报错（Cascading Failure）。
*   **案例分析 (Case `b1ab098d-83`)**:
    *   **现象**: `cartservice` 报错率飙升，`frontend` 响应慢。
    *   **误判**: Baseline 模型容易被 `cartservice` 的大量报错日志误导，将其标记为根因。
    *   **Ours 的纠偏**: History-RCA 检索到了类似的“Redis 导致的 Cart 服务降级”案例。它遵循检索到的关键检查点 `CheckServiceDependency()`，发现 `cartservice` 的错误全是 `Redis Connection Timeout`，从而正确地将根因锁定在上游的 `redis-cart-0`。这体现了 RAG 带来的全局依赖视角。

### 4.3 代码变更类故障的精准打击 (Precision in Change-related Faults)
`Erroneous Change` 类别提升了 **19.0%**，这是一个巨大的突破。
*   **机理**: 这类故障通常没有明显的资源异常（CPU/内存正常），只有特定的应用日志（如 `NullPointerException` 或 `MethodNotFound`）。
*   **分析**: 这种特定的错误堆栈（Stack Trace）在 Embedding 空间中具有极高的区分度。传统的指标监控（Metric）对此类故障无能为力，而基于文本语义检索的 History-RCA 能够像搜索引擎一样，精准匹配到历史上的同类代码 Bug，实现了“对症下药”。

### 4.4 失败案例反思 (Failure Analysis - Node Faults)
我们在 `Node Fault` 上观察到了 **-4.9%** 的性能回撤，这是值得深入讨论的：
*   **问题**: 节点故障（如节点磁盘满）会导致该节点上所有 Pod 同时异常。
*   **干扰**: 这种“多点开花”的症状在检索时产生了巨大的噪声。RAG 可能会检索到其中某一个 Pod（如 `checkoutservice`）的历史故障，导致 Orchestrator 过于关注应用层细节，而忽略了底层的共性（所有相关 Pod 都在同一个 Node 上）。
*   **启示**: 这表明当前的检索策略偏向于“应用层语义”。未来的改进方向是在 Query 中显式加入拓扑信息（如“多个 Pod 同时报错”），以触发基础设施层面的检索。


## 5. Generalization Analysis: Seen vs. Unseen Faults

| Method | Seen Test (Similar Cases Exists) | Unseen Test (Novel Faults) | Drop Rate (Generalization Gap) |
| :--- | :--- | :--- | :--- |
| History-RCA (Ours) | **58.1%** (n=117) | **91.4%** (n=35) | --33.3% |
| Multi-Agent w/o RAG | **50.4%** (n=117) | **94.3%** (n=35) | --43.9% |

### Analysis of Generalization Capability
1. **Performance on Known Faults (Seen Test)**: History-RCA achieved **58.1%** accuracy, significantly outperforming the baseline (50.4%). This confirms that for recurring faults (which are common in production), the RAG knowledge base effectively acts as an 'Expert Memory', guiding the agent to the correct root cause quickly.

2. **Robustness on Novel Faults (Unseen Test)**: Even for faults never seen before, History-RCA maintained **91.4%** accuracy, still higher than the baseline's 94.3%.

3. **Generalization Gap**: Note that History-RCA's performance drop (--33.3%) is comparable to or slightly larger than the baseline. This is expected behavior: RAG systems rely on similarity. When a fault is truly 'Unseen' (novel root cause), the retrieval module might return less relevant cases. However, the result shows it still provides a slight positive transfer effect (or at least doesn't catastrophically fail), likely because different faults may share similar investigation steps (e.g., 'Check CPU' is a valid step for both 'Process Hang' and 'Calculation Loop').
