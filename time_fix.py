#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix: Shift old UTC timestamps in SQLite to Beijing time (+8h) - runs once on startup"""
import os, sqlite3, time

MARKER = '/tmp/_time_fixed_20260521'

def fix_old_timestamps():
    """Run once: add 8 hours to all timestamps that were stored as UTC"""
    if os.path.exists(MARKER):
        print("[TimeFix] Already fixed, skipping")
        return
    
    # Determine DB path
    DATA_DIR = '/app/data' if os.path.exists('/app/data') else '.'
    DB_PATH = os.path.join(DATA_DIR, 'data.db')
    
    if not os.path.exists(DB_PATH):
        print(f"[TimeFix] DB not found at {DB_PATH}, skipping")
        return
    
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        total = 0
        
        # Fix customers
        c.execute("""
            UPDATE customers SET 
                created_at = datetime(created_at, '+8 hours'),
                updated_at = datetime(updated_at, '+8 hours')
            WHERE created_at < '2026-05-21' 
              AND created_at IS NOT NULL 
              AND created_at != ''
        """)
        total += c.execute("SELECT changes()").fetchone()[0]
        
        # Fix check_history
        c.execute("""
            UPDATE check_history SET 
                checked_at = datetime(checked_at, '+8 hours')
            WHERE checked_at < '2026-05-21' 
              AND checked_at IS NOT NULL 
              AND checked_at != ''
        """)
        total += c.execute("SELECT changes()").fetchone()[0]
        
        # Fix check_logs
        c.execute("""
            UPDATE check_logs SET 
                created_at = datetime(created_at, '+8 hours')
            WHERE created_at < '2026-05-21' 
              AND created_at IS NOT NULL 
              AND created_at != ''
        """)
        total += c.execute("SELECT changes()").fetchone()[0]
        
        conn.commit()
        conn.close()
        
        # Write marker
        with open(MARKER, 'w') as f:
            f.write(f'fixed_at={time.time()}')
        
        print(f"[TimeFix] ✅ Fixed {total} old records (+8h)")
    except Exception as e:
        print(f"[TimeFix] ❌ Error: {e}")

if __name__ == '__main__':
    fix_old_timestamps()
