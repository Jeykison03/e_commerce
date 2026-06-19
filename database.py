import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def get_engine():
    DB_HOST     = os.getenv("DB_HOST",     "localhost")
    DB_PORT     = os.getenv("DB_PORT",     "5432")
    DB_NAME     = os.getenv("DB_NAME",     "ecommerce_dw")
    DB_USER     = os.getenv("DB_USER",     "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "your_password_here")

    connection_string = (
        f"postgresql://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    engine = create_engine(
        connection_string,
        pool_pre_ping = True,
        pool_size     = 5,
        max_overflow  = 10
    )
 
    return engine

def test_connection():
    try:
        engine = get_engine()
        with engine.connect() as conn:
 
            result  = conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]
            print(f"Connected to PostgreSQL successfully!")
            print(f"Version: {version[:50]}...")
 
            result = conn.execute(text("""
                SELECT table_name
                FROM   information_schema.tables
                WHERE  table_schema = 'public'
                ORDER  BY table_name
            """))
            tables = result.fetchall()
 
            if tables:
                print(f"\nTables in ecommerce_dw:")
                print("-" * 45)
                for t in tables:
                    count = conn.execute(
                        text(f'SELECT COUNT(*) FROM "{t[0]}"')
                    ).fetchone()[0]
                    print(f"  {t[0]:<35} {count:>10,} rows")
            else:
                print("\nNo tables yet — run create_tables_POSTGRESQL.sql first")
 
            result = conn.execute(text("""
                SELECT
                    tc.table_name,
                    kcu.column_name,
                    ccu.table_name AS references_table
                FROM information_schema.table_constraints        AS tc
                JOIN information_schema.key_column_usage         AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage  AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                ORDER BY tc.table_name
            """))
            fkeys = result.fetchall()
 
            if fkeys:
                print(f"\nForeign key constraints:")
                print("-" * 50)
                for fk in fkeys:
                    print(f"  {fk[0]}.{fk[1]}  →  {fk[2]}")
 
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    test_connection()
 
