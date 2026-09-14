# 覆盖分析功能文档

## 概述

覆盖分析功能自动检查新发现的数据源是否已经被现有数据源覆盖（通过 fd-open-data-mcp 或 fd-industry-data 爬虫），并根据覆盖情况自动调整优先级分数。

## 功能特性

### 1. 自动检测覆盖状态

- **covered** (已覆盖): URL 完全匹配或字段覆盖率 >= 80%
- **partial** (部分覆盖): 字段覆盖率在 50%-80% 之间
- **new** (新数据源): 字段覆盖率 < 50%，有独特价值
- **unknown** (未知): 未进行分析

### 2. 智能分数调整

根据覆盖状态自动调整候选数据源的优先级分数：

| 状态 | 分数调整 | 说明 |
|------|----------|------|
| covered | -50 分 | 已完全覆盖，优先级大幅降低 |
| partial | -20 分 | 部分覆盖，可能仍有独特数据 |
| new | 0 分 | 新数据源，保持原始优先级 |

### 3. 覆盖检测机制

#### URL 匹配
- 精确匹配：URL 完全相同
- 前缀匹配：候选 URL 以现有源 URL 开头

#### 字段覆盖分析
- 从 fd-open-data-mcp 获取已注册的 concept codes
- 从 fd-industry-data 获取已生成的爬虫 manifest
- 对比候选数据源的字段与现有覆盖

## 使用方法

### 命令行工具

```bash
# 运行覆盖分析
uv run fd-scraw-harness analyze-coverage

# 查看覆盖报告
uv run fd-scraw-harness list --coverage new  # 查看新数据源
uv run fd-scraw-harness list --coverage covered  # 查看已覆盖的

# 按调整后分数排序
uv run fd-scraw-harness list --sort adjusted-score
```

### Python API

```python
from fd_scraw_harness.coverage import analyze_all_candidates, print_coverage_report

# 运行覆盖分析
results = analyze_all_candidates()

# 打印报告
print_coverage_report(results)

# 查看结果
print(f"新数据源: {results['new']}")
print(f"已覆盖: {results['covered']}")
```

### 自动化脚本

```bash
# 定期运行覆盖分析（可集成到 crontab）
uv run scripts/analyze_coverage.py

# 带详细日志
uv run scripts/analyze_coverage.py --verbose
```

## 数据库字段

在 `candidates` 表中添加了以下字段：

```sql
coverage_status TEXT DEFAULT 'unknown'  -- 覆盖状态
coverage_details TEXT                   -- JSON 格式的详细信息
adjusted_score INTEGER                  -- 调整后的优先级分数
```

## 示例输出

```
================================================================================
📊 覆盖分析报告
================================================================================

总计候选数据源：320
  ✅ 已覆盖 (covered): 4
  ⚠️  部分覆盖 (partial): 0
  🆕 新数据源 (new): 316
  ❓ 未知 (unknown): 0

--------------------------------------------------------------------------------
📋 详细列表 (按调整后分数排序):
--------------------------------------------------------------------------------

1. 🆕 [100] https://data.stats.gov.cn
   URL: https://data.stats.gov.cn
   原因: New data source with unique fields

2. ✅ [ 48] https://www.stats.gov.cn/
   URL: https://www.stats.gov.cn/
   原因: Already covered by existing source

...
```

## 集成到工作流

### 1. 发现阶段后自动分析

```python
from fd_scraw_harness.discovery import discover
from fd_scraw_harness.coverage import analyze_all_candidates

# 发现数据源
session_id = discover("有色金属 交易所")

# 立即运行覆盖分析
results = analyze_all_candidates()

# 根据结果决定下一步
if results['new'] > 0:
    print(f"发现 {results['new']} 个新数据源值得处理")
```

### 2. 定期更新优先级

```bash
# 每天凌晨 2 点运行覆盖分析
0 2 * * * cd /path/to/fd-scraw-harness && uv run scripts/analyze_coverage.py
```

### 3. 过滤高优先级候选源

```python
from fd_scraw_harness.db import get_session
from fd_scraw_harness.models import Candidate

with get_session() as sess:
    # 只获取新数据源（未覆盖）
    new_sources = (
        sess.query(Candidate)
        .filter_by(coverage_status="new")
        .order_by(Candidate.adjusted_score.desc())
        .all()
    )
    
    # 处理这些高价值数据源
    for source in new_sources:
        print(f"处理新数据源: {source.url}")
```

## 最佳实践

1. **发现后立即分析**: 每次运行 `discover` 后立即运行覆盖分析
2. **优先处理新数据源**: 优先处理 `coverage_status='new'` 的候选源
3. **谨慎处理已覆盖的**: 对于 `coverage_status='covered'` 的源，评估是否真的有独特价值
4. **定期更新**: 随着新数据源被集成，定期重新运行覆盖分析

## 故障排除

### 问题：覆盖分析显示所有源都是 "new"

**原因**: 可能是 fd-open-data-mcp 或 fd-industry-data 的数据库路径不正确

**解决**: 检查 `coverage.py` 中的数据库路径配置

### 问题：分数调整过于激进

**解决**: 修改 `analyze_candidate_coverage()` 函数中的分数调整逻辑

### 问题：字段覆盖率计算不准确

**解决**: 确保候选数据源的字段信息已正确提取并存储在数据库中

## 未来改进

- [ ] 支持自定义覆盖规则
- [ ] 添加字段级别的详细对比
- [ ] 支持多数据源合并覆盖检测
- [ ] 添加可视化覆盖报告
- [ ] 支持增量分析（只分析新添加的候选源）
