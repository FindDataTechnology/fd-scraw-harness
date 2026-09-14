#!/usr/bin/env python3
"""Simple script to approve high-quality new data sources."""
import sqlite3

DB_PATH = "data/harness.db"

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get top 20 new candidates with highest adjusted_score
    cursor.execute("""
        SELECT id, title, url, adjusted_score 
        FROM candidates 
        WHERE coverage_status = 'new' AND adjusted_score IS NOT NULL
        ORDER BY adjusted_score DESC
        LIMIT 20
    """)
    
    results = cursor.fetchall()
    
    print(f"Found {len(results)} high-priority candidates\n")
    
    for row in results:
        candidate_id, title, url, score = row
        print(f"ID: {candidate_id}, Score: {score}")
        print(f"Title: {title[:70]}...")
        print(f"URL: {url}\n")
    
    print("="*80)
    print(f"\nTo approve these IDs manually, run:")
    print("  cd ~/finddata/fd-scraw-harness")
    print("  sqlite3 data/harness.db \"UPDATE candidates SET status='draft' WHERE id IN (" + ",".join(str(r[0]) for r in results) + ")\"")
    
    conn.close()


if __name__ == "__main__":
    main()
