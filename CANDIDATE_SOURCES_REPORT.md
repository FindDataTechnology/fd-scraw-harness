# 待选数据源清单报告

**生成时间**: 2026-07-30  
**数据来源**: fd-scraw-harness LLM 搜索 + 子代理调研

## 📊 总体统计

| 指标 | 数值 |
|------|------|
| Discovery Sessions | 72 |
| 总候选数据源 | 320 |
| 高优先级 (Score >= 90) | 140 |
| 开源数据项目 | 9 |
| 政府统计网站 | 46 |
| 行业协会 | 4 |
| 社交媒体平台 | 4 |
| 新闻媒体 | 4 |

## 🔓 开源数据项目 (9 个)

这些项目可以**立即使用**，无需爬虫：

| # | 项目名 | URL | 说明 |
|---|--------|-----|------|
| 1 | Kaggle Datasets | https://www.kaggle.com/datasets | 大规模结构化数据集，支持 Python 分析 |
| 2 | Awesome Public Datasets | https://github.com/awesomedata/awesome-public-datasets | GitHub 开源数据集精选列表 |
| 3 | GitHub Topics - Datasets | https://github.com/topics/dataset | GitHub 官方数据集标签页 |
| 4 | AkShare | https://github.com/akfamily/akshare | Python 金融数据接口库 |
| 5 | Awesome China Dataset | https://github.com/awesome-china/data | 中国开源数据集精选 |
| 6 | Chinese Datasets Collection | https://github.com/datasets/chinese-datasets | 中文语言数据集集合 |
| 7 | UCI ML Repository | https://archive.ics.uci.edu/ml/index.php | 经典机器学习数据集 |
| 8 | FiveThirtyEight Data | https://github.com/fivethirtyeight/data | 政治社会新闻数据集 |
| 9 | Data.gov | https://www.data.gov | 美国政府开放数据门户 |

**建议**: 这些项目可以直接下载 CSV/JSON 数据，无需爬虫。优先集成 AkShare 和 Kaggle。

## 🏛️ 政府统计网站 (46 个)

已部分集成到 fd-industry-data，可扩展：

| # | 网站 | URL | 数据类型 |
|---|------|-----|----------|
| 1 | 国家统计局 | https://www.stat.gov.cn/ | GDP、人口、就业等宏观经济 |
| 2 | 国家统计数据数据库 | https://data.stats.gov.cn/ | 历史统计数据查询 |
| 3 | 中国人民银行 | https://www.pbc.gov.cn/ | 货币供应量、信贷收支 |
| 4 | 农业农村部 | https://www.moa.gov.cn/ | 农林牧渔生产数据 |
| 5 | 教育部 | http://www.moe.gov.cn/ | 教育统计 |
| 6 | 卫健委 | https://www.nhc.gov.cn/ | 卫生健康统计 |
| 7 | 财政部 | https://www.mof.gov.cn/ | 财政收支 |

**建议**: 已有 NBS GDP 爬虫，可扩展到其他部委数据。

## 📱 社交媒体平台 (4 个)

需要 API 认证，建议后期处理：

| # | 平台 | URL | 数据类型 |
|---|------|-----|----------|
| 1 | 微信开放平台 | https://developers.weixin.qq.com/ | 公众号数据、用户分析 |
| 2 | 微信公众平台 | https://mp.weixin.qq.com/ | 后台数据分析 |
| 3 | 微博开放平台 | https://open.weibo.com/ | 用户数据、状态帖子 |
| 4 | 今日头条开放平台 | https://open.toutiao.com/ | 内容分发、广告营销 |

**建议**: 需要申请 API Key，建议作为第二阶段任务。

## 📰 新闻媒体 (4 个)

| # | 媒体 | URL | 数据类型 |
|---|------|-----|----------|
| 1 | 人民网数据中心 | https://data.people.com.cn/ | 人民日报历史文献 |
| 2 | 中国知网·人民日报全文库 | https://www.cnki.net/ | 报纸全文数据 |
| 3 | 万方数据·中国重要报纸库 | https://www.wanfangdata.com.cn/ | 核心报纸数字化全文 |
| 4 | 国家图书馆·中国近代报纸库 | https://www.nlc.cn/ | 历史影印版 |

**建议**: 学术数据库，可能需要订阅访问。

## 🏢 行业协会 (4 个)

已在 fd-industry-data 中覆盖：

- 中国钢铁工业协会
- World Steel Association
- 中国有色金属工业协会
- 中国电子行业协会

## 📈 交易所 (2 个)

已在 fd-industry-data 中覆盖：

- CME Group Agriculture
- 上海期货交易所

## 💡 集成优先级建议

### 第一阶段（立即可做）
1. **开源数据项目** - 直接下载，无需爬虫
   - AkShare (Python 库)
   - Kaggle Datasets
   - GitHub Awesome China Dataset

2. **政府统计扩展** - 基于现有 NBS 爬虫
   - 农业农村部数据
   - 央行货币数据
   - 财政部数据

### 第二阶段（需要认证）
3. **社交媒体平台** - API 认证
   - 微信开放平台
   - 微博开放平台
   - 今日头条开放平台

### 第三阶段（学术访问）
4. **新闻媒体数据库** - 订阅访问
   - CNKI 知网
   - 万方数据
   - 国家图书馆

## ✅ 下一步操作

```bash
# 1. 查看所有发现会话
cd /Users/chengsishi/finddata/fd-scraw-harness
uv run fd-scraw-harness list --status discovered

# 2. 批准特定数据源（生成 manifest）
uv run fd-scraw-harness approve <manifest-id>

# 3. 生成爬虫代码（参考 fd-industry-data 模板）
# 对于开源项目，直接下载数据
# 对于网站数据，使用 spiers/*/spider.py 模板

# 4. 导入到 fd-open-data-mcp（可选）
uv run python scripts/import_manifest.py manifests/<source>.yaml
```

## 📝 备注

- 所有 320 个候选数据源已保存到 fd-scraw-harness 数据库
- 140 个高优先级源（score >= 90）已分类整理
- 9 个开源项目可立即使用
- 建议按优先级分阶段集成

---
*报告由 fd-scraw-harness 自动生成*
