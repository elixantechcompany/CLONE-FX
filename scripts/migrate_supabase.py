import os
import sys
import urllib.parse
import psycopg2

DB_URL = os.getenv("DATABASE_URL", "")
SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "..", "signals-web", "supabase", "schema.sql")

def run_migration():
    print("=" * 60)
    print(" SUPABASE SCHEMA MIGRATION RUNNER")
    print("=" * 60)
    print(f"[*] Reading schema file: {SCHEMA_FILE}")
    if not os.path.exists(SCHEMA_FILE):
        print(f"[!] Schema file not found: {SCHEMA_FILE}")
        sys.exit(1)

    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        sql_content = f.read()

    print("[*] Connecting to Supabase PostgreSQL database...")
    try:
        conn = psycopg2.connect(DB_URL, connect_timeout=15)
        conn.autocommit = True
        print("[+] Connected successfully!")
        
        cur = conn.cursor()
        print("[*] Executing schema.sql statements...")
        cur.execute(sql_content)
        print("[+] Schema executed successfully!")

        print("[*] Verifying tables and records in Supabase...")
        cur.execute("SELECT count(*) FROM signals;")
        signal_count = cur.fetchone()[0]
        print(f"[+] Total signals in database: {signal_count}")

        cur.execute("SELECT symbol, direction, entry_price, status, confluence_score FROM signals LIMIT 5;")
        rows = cur.fetchall()
        print("\n[+] Sample records created in Supabase:")
        for r in rows:
            print(f"    - {r[0]} | {r[1]} @ {r[2]} | Status: {r[3]} | Score: {r[4]}")

        cur.close()
        conn.close()
        print("\n" + "=" * 60)
        print(" DATABASE MIGRATION COMPLETED SUCCESSFULLY! [✓]")
        print("=" * 60)

    except Exception as e:
        print(f"[!] Migration error: {e}")
        # Try with pooler URL if direct host fails on IPv6/network
        print("[*] Checking if connection pooling port 6543 helps...")
        pooler_url = "postgresql://postgres.xeckbeavsvyoporldjzm:hannington%4020%3F7@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"
        try:
            conn = psycopg2.connect(pooler_url, connect_timeout=15)
            conn.autocommit = True
            print("[+] Connected via pooler successfully!")
            cur = conn.cursor()
            cur.execute(sql_content)
            cur.execute("SELECT count(*) FROM signals;")
            count = cur.fetchone()[0]
            print(f"[+] Total signals in database: {count}")
            cur.close()
            conn.close()
            print("[✓] Pooler migration succeeded!")
        except Exception as e2:
            print(f"[!] Pooler error: {e2}")
            sys.exit(1)

if __name__ == "__main__":
    run_migration()
