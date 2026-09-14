# 🤖 自动化行业数据源发现系统

## ✅ 已完成的工作

### 1. 批量发现系统已运行
- **发现的数据源总数**: 241 个候选
- **处理的行业数**: 多个申万一级行业（钢铁、有色金属、农林牧渔等）
- **发现方式**: 每个行业执行 5 个不同的关键词查询
  - `{行业名} 行业协会`
  - `{行业名} 交易所 数据`
  - `{行业名} 统计数据 官网`
  - `{行业名} 产业信息网`
  - `{行业名} 市场数据平台`

### 2. Dashboard 监控界面
```bash
uv run python scripts/dashboard.py 8892
→ http://127.0.0.1:8892
```

功能：
- 查看所有发现的行业和数据源
- 点击卡片查看详情和 URL
- 批准/拒绝数据源
- 导出 YAML 配置文件

### 3. 定时任务设置
Cron 作业已配置，每 6 小时自动运行：
```bash
crontab -l | grep fd-scraw
# 0 */6 * * * cd ~/finddata/fd-scraw-harness && bash scripts/run_discovery.sh
```

## 📊 当前状态

**Top Industries by Found Sources:**
1. 钢铁 - 50 sources (10 queries)
2. 有色金属 - 49 sources (10 queries)
3. 农林牧渔 - 48 sources (10 queries)
4. 基础化工 - 40 sources (10 queries)
5. 电子 - 22 sources (5 queries)

## 🔄 如何让它持续运行

### 手动触发新的发现批次
```bash
cd ~/finddata/fd-scraw-harness
export LINJIE_API_KEY="sk-your-linjie-api-key"
uv run python scripts/batch_discover.py
```

### 查看所有结果
```bash
# CLI 方式
uv run fd-scraw-harness list --status discovered

# Dashboard 方式
uv run python scripts/dashboard.py 8892
open http://127.0.0.1:8892

# HTML 报告
open /tmp/industry_discovery_report.html
```

### 停止自动运行
```bash
# 移除 cron job
crontab -e
# 删除包含 "fd-scraw" 的行
```

## 🎯 你的工作流程

1. **定期检查 Dashboard**
   - 每周访问 http://127.0.0.1:8892
   - 查看 "Discoveries" 标签页

2. **审核批准数据源**
   - 点击 Discovery 卡片
   - 查看候选 URL 列表
   - 点击 "✓ Approve" 批准有价值的来源

3. **导出数据**
   ```bash
   # 导出 YAML
   uv run fd-scraw-harness export <id> -o data-source.yaml
   
   # 用于后续爬虫开发
   ```

## 🛠️ 技术架构

- **LLM Provider**: Linjie AI (gm51model, qmodel_latest)
- **Discovery Engine**: LLM-based web search + candidate ranking
- **Storage**: SQLite (data/harness.db) with PostgreSQL support
- **Scheduling**: System cron (every 6 hours)
- **Dashboard**: FastAPI web interface for management

## 📈 扩展选项

1. **增加行业数量**
   - Edit `batch_discover.py` to add more industries from SW classification
   - Currently processes first 10 of 31 level-1 industries

2. **调整频率**
   - Edit crontab entry to change from every 6 hours to daily/weekly

3. **添加更多关键词**
   - Edit keywords in `batch_discover.py`
   - Add industry-specific search terms

---

**系统已完全自动化运行中！你只需要定期审核即可。**
