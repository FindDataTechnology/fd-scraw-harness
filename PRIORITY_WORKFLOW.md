# 优先级驱动爬虫生成工作流

## 🎯 功能概述

实现了完整的优先级驱动的爬虫代码生成系统：

1. ✅ **自动覆盖分析** - 检测数据源是否已存在
2. ✅ **智能分数调整** - 根据覆盖情况自动调整优先级
3. ✅ **数据库持久化** - 评分结果保存到 database
4. ✅ **优先级排序** - 从数据库中获取已排序的候选数据源
5. ⚡ **并行生成** - 准备使用 subagent 并行处理高优先级源

## 🔄 完整工作流程

### 步骤 1: 发现候选数据源

```bash
# 搜索关键词
uv run fd-scraw-harness discover "有色金属 交易所"

# 或指定 URL
uv run fd-scraw-harness discover --url https://example.com
```

这会创建 discovery session 并找到多个候选数据源。

### 步骤 2: 运行覆盖分析（自动打分）

```bash
# 运行覆盖分析并更新数据库
uv run fd-scraw-harness analyze-coverage
```

**输出示例**:
```
🔍 Running coverage analysis...
================================================================================

✅ Analysis complete!
   Total candidates analyzed: 320
   Covered: 4
   Partial: 0
   New: 316
================================================================================
```

### 步骤 3: 查看优先级排名

```bash
# 查看所有候选并按优先级排序
uv run fd-scraw-harness list-candidates

# 只显示新数据源
uv run fd-scraw-harness list-candidates --status new

# 查看 Top 10 高优先级来源
uv run fd-scraw-harness list-priorities --limit 10
```

**输出示例**:
```
================================================================================
📊 Priority List (Top 10)
================================================================================

1. 🆕 [100] https://data.stats.gov.cn
   URL: https://data.stats.gov.cn
   Status: unknown
   Desc: ...

2. 🆕 [98] 中国证券投资基金业协会 (AMAC)
   URL: https://www.amac.org.cn/
   Status: new
   Desc: Provides detailed data on private fund manager...
```

### 步骤 4: 并行生成爬虫代码

```bash
# 为 Top 20 高优先级源生成爬虫（使用 5 个并发 worker）
uv run scripts/generate_spiders.py --top 20 --workers 5

# 跳过覆盖分析（如果已经分析过）
uv run scripts/generate_spiders.py --skip-analysis --top 10
```

## 📊 数据库字段说明

`candidates` 表新增字段：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `coverage_status` | TEXT | 覆盖状态 (covered/partial/new/unknown) |
| `coverage_details` | TEXT | JSON 格式的详细信息 |
| `adjusted_score` | INTEGER | 调整后的优先级分数 |

## 💡 分数计算规则

| 覆盖情况 | 分数调整 | 说明 |
|----------|---------|------|
| **New** | 0 分 | 新数据源，保持原始优先级 |
| **Partial** | -20 分 | 部分覆盖，可能有独特数据 |
| **Covered** | -50 分 | 已完全覆盖，优先级大幅降低 |

## 🔧 技术实现

### 核心组件

1. **`fd_scraw_harness/coverage.py`** - 覆盖分析逻辑
2. **`scripts/generate_spiders.py`** - 优先级驱动的爬虫生成器
3. **`fd_scraw_harness/cli.py`** - CLI 命令集成

### 数据库查询示例

```python
from fd_scraw_harness.db import get_session, init_db
from fd_scraw_harness.models import Candidate

init_db()

with get_session() as sess:
    # 获取新数据源，按调整后分数排序
    new_sources = (
        sess.query(Candidate)
        .filter_by(coverage_status="new")
        .order_by(Candidate.adjusted_score.desc())
        .all()
    )
    
    for source in new_sources:
        print(f"[{source.adjusted_score}] {source.title}")
        print(f"   URL: {source.url}")
```

## 🚀 自动化脚本

### 定期任务（Crontab）

```bash
# 每天凌晨 2 点运行覆盖分析
0 2 * * * cd /path/to/fd-scraw-harness && uv run fd-scraw-harness analyze-coverage

# 每周六上午 9 点生成 Top 20 爬虫
0 9 * * 6 cd /path/to/fd-scraw-harness && uv run scripts/generate_spiders.py --top 20
```

## 📈 实际效果对比

### 使用前
- ❌ 无法区分新旧数据源
- ❌ 所有来源都按原始分数排序
- ❌ 可能重复采集已有数据

### 使用后
- ✅ 自动识别已覆盖数据源
- ✅ 优先处理真正的新数据源
- ✅ 避免重复工作和资源浪费

## 🎯 下一步整合子代理框架

当前已实现的架构：

```
┌─────────────────────────────────────────────┐
│  1. Discovery (LLM Search)                 │
│     ↓                                        │
│  2. Coverage Analysis & Scoring            │
│     ↓                                        │
│  3. Priority Queue (Database Sorted)       │
│     ↓                                        │
│  4. Spider Generation (Parallel Workers)   │
│     ↓                                        │
│  5. Data Collection                        │
└─────────────────────────────────────────────┘
```

**待完成**: 
- 将 `generate_spiders_parallel()` 与 actual subagent framework 对接
- 实现真正的并行任务分发
- 添加进度跟踪和错误恢复机制

## ✅ 验收清单

- [x] 覆盖分析功能实现
- [x] 数据库字段扩展
- [x] 优先级分数计算
- [x] CLI 命令集成
- [x] 优先级查询接口
- [x] 爬虫生成器框架
- [ ] 子代理并行集成
- [ ] 进度跟踪 UI
- [ ] 自动化调度脚本

---

**最后更新**: 2026-07-31  
**状态**: 核心功能已完成，等待子代理框架集成
