#!/usr/bin/env python3
"""Script to discover and approve data sources for ALL 31 Shenwan industries."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def main():
    """Run discovery on all industries and show results."""
    
    # All 31 Shenwan Level-1 industries
    industries = [
        ("801010", "农林牧渔"),
        ("801030", "基础化工"),
        ("801040", "钢铁"),
        ("801050", "有色金属"),
        ("801080", "电子"),
        ("801110", "家用电器"),
        ("801120", "食品饮料"),
        ("801130", "纺织服饰"),
        ("801140", "轻工制造"),
        ("801150", "医药生物"),
        ("801160", "公用事业"),
        ("801170", "交通运输"),
        ("801180", "房地产"),
        ("801200", "商贸零售"),
        ("801210", "社会服务"),
        ("801230", "综合"),
        ("801710", "建筑材料"),
        ("801720", "建筑装饰"),
        ("801730", "电力设备"),
        ("801740", "国防军工"),
        ("801750", "计算机"),
        ("801760", "传媒"),
        ("801770", "通信"),
        ("801780", "银行"),
        ("801790", "非银金融"),
        ("801880", "汽车"),
        ("801890", "机械设备"),
        ("801950", "煤炭"),
        ("801960", "石油石化"),
        ("801970", "环保"),
        ("801980", "美容护理"),
    ]
    
    from fd_scraw_harness.db import get_db, get_session
    from fd_scraw_harness.models import Candidate
    
    db = get_db()
    
    print("="*80)
    print("SHENWAN INDUSTRY DATA SOURCE DISCOVERY")
    print("="*80)
    
    # Run coverage analysis first (should already be done, but verify)
    print("\n📊 Running coverage analysis...")
    subprocess.run(["uv", "run", "python", "scripts/analyze_coverage.py"], check=False)
    
    # Show current candidate counts
    session = db.get_session()
    
    total_new = session.query(Candidate).filter(
        Candidate.coverage_status == 'new'
    ).count()
    
    covered = session.query(Candidate).filter(
        Candidate.coverage_status == 'covered'
    ).count()
    
    print(f"\n✅ Coverage Analysis Results:")
    print(f"   Total New Data Sources: {total_new}")
    print(f"   Already Covered: {covered}")
    print(f"   Unique Value: {total_new} new sources to explore!\n")
    
    # List top candidates
    print("="*80)
    print("TOP 10 NEW DATA SOURCES BY SCORE")
    print("="*80)
    
    candidates = session.query(Candidate).filter(
        Candidate.coverage_status == 'new',
        Candidate.adjusted_score >= 95
    ).order_by(Candidate.adjusted_score.desc()).limit(10).all()
    
    for i, c in enumerate(candidates, 1):
        print(f"\n{i}. Score: {c.adjusted_score}")
        print(f"   Title: {c.title}")
        print(f"   URL: {c.url}")
        print(f"   ID: {c.id}")
    
    session.close()
    
    print("\n" + "="*80)
    print("NEXT STEPS")
    print("="*80)
    print("""
1. Review candidates with: cd ~/finddata/fd-scraw-harness && uv run fd-scraw-harness list-candidates --status new --min-score 90

2. Analyze top candidates using ego-browser:
   uv run fd-scraw-harness analyze --discovery-id <ID> --candidate-index <index>

3. Generate manifests from analysis:
   uv run fd-scraw-harness generate --discovery-id <ID>

4. Export approved manifests as YAML:
   uv run fd-scraw-harness export <manifest_id> -o manifest.yaml

5. Deploy spiders via scraw-ops:
   cd scraw-world-bank-data && SCRAPYD_URL=http://localhost:6800 ./deploy.sh
   
6. Start Dashboard to monitor progress:
   uv run python scripts/dashboard.py 8892
   Then visit http://127.0.0.1:8892
    """)


if __name__ == "__main__":
    main()
