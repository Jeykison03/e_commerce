import os
import pandas as pd
from sqlalchemy import text
from database import get_engine
from explore import DataExplore
from clean_data import Data_cleaner


class FactLoader:
    def __init__(self, master_df):
        self.engine = get_engine()
        self.master = master_df

    # ──────────────────────────────────────────────
    # Step 1 — Read dimension lookup tables from DB
    # ──────────────────────────────────────────────

    def _read_dim_table(self, table_name, key_col, id_col):
        """
        Read a dimension table from PostgreSQL.
        Returns a DataFrame with just the surrogate key and the business ID.
        """
        query = f"SELECT {key_col}, {id_col} FROM {table_name}"

        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn)

        print(f"  {table_name:20s}  →  {len(df):,} rows loaded")
        return df

    def load_lookups(self):
        """
        Load all 4 dimension lookups into memory.
        These map business IDs → surrogate keys.
        """
        print("\nStep 1 — Loading dimension lookups from DB")
        print("-" * 50)

        self.dim_customers = self._read_dim_table(
            "dim_customers", "customer_key", "customer_id"
        )
        self.dim_products = self._read_dim_table(
            "dim_products", "product_key", "product_id"
        )
        self.dim_sellers = self._read_dim_table(
            "dim_sellers", "seller_key", "seller_id"
        )
        self.dim_date = self._read_dim_table(
            "dim_date", "date_key", "full_date"
        )

        # Convert full_date to date type so it matches master's purchase_date
        self.dim_date["full_date"] = pd.to_datetime(
            self.dim_date["full_date"]
        ).dt.date

        return self

    # ──────────────────────────────────────────────
    # Step 2 — Join master with lookups to get keys
    # ──────────────────────────────────────────────

    def build_fact_df(self):
        """
        Merge master DataFrame with all 4 dimension lookups.
        Replace business IDs with surrogate keys.
        """
        print("\nStep 2 — Joining master with dimension keys")
        print("-" * 50)

        df = self.master.copy()

        # Ensure purchase_date is a date object for joining with dim_date
        df["purchase_date"] = pd.to_datetime(
            df["order_purchase_timestamp"]
        ).dt.date

        # --- Join customer_key ---
        before = len(df)
        df = df.merge(
            self.dim_customers,
            on="customer_id",
            how="inner"
        )
        print(f"  + customer_key:  {before:,} → {len(df):,} rows")

        # --- Join product_key ---
        before = len(df)
        df = df.merge(
            self.dim_products,
            on="product_id",
            how="inner"
        )
        print(f"  + product_key:   {before:,} → {len(df):,} rows")

        # --- Join seller_key ---
        before = len(df)
        df = df.merge(
            self.dim_sellers,
            on="seller_id",
            how="inner"
        )
        print(f"  + seller_key:    {before:,} → {len(df):,} rows")

        # --- Join date_key ---
        before = len(df)
        df = df.merge(
            self.dim_date,
            left_on="purchase_date",
            right_on="full_date",
            how="inner"
        )
        print(f"  + date_key:      {before:,} → {len(df):,} rows")

        # --- Calculate total_revenue ---
        df["total_revenue"] = df["price"] + df["freight_value"]

        # --- Parse timestamps ---
        df["purchase_timestamp"] = pd.to_datetime(
            df["order_purchase_timestamp"], errors="coerce"
        )
        df["delivered_timestamp"] = pd.to_datetime(
            df["order_delivered_customer_date"], errors="coerce"
        )

        # --- Select only fact_orders columns ---
        self.fact_df = df[[
            "order_id",
            "order_item_id",
            "customer_key",
            "product_key",
            "seller_key",
            "date_key",
            "order_status",
            "payment_type",
            "payment_installments",
            "price",
            "freight_value",
            "total_revenue",
            "payment_value",
            "review_score",
            "delivery_days",
            "delivery_delay_days",
            "is_late",
            "purchase_timestamp",
            "delivered_timestamp"
        ]].copy()

        print(f"\n  Fact DataFrame ready: {self.fact_df.shape}")

        return self

    # ──────────────────────────────────────────────
    # Step 3 — Insert into fact_orders
    # ──────────────────────────────────────────────

    @staticmethod
    def _safe(value):
        """Convert pandas NaT / NaN / None to Python None for PostgreSQL."""
        if pd.isna(value):
            return None
        return value

    @staticmethod
    def _safe_float(value):
        """Convert to float, but return None if NaN/NaT."""
        if pd.isna(value):
            return None
        return float(value)

    def insert_facts(self, batch_size=500):
        """
        INSERT rows into fact_orders with ON CONFLICT DO NOTHING.
        Uses batched commits for better performance on 100k+ rows.
        """
        print("\nStep 3 — Inserting into fact_orders")
        print("-" * 50)

        query = text("""
            INSERT INTO fact_orders (
                order_id, order_item_id,
                customer_key, product_key, seller_key, date_key,
                order_status, payment_type, payment_installments,
                price, freight_value, total_revenue, payment_value,
                review_score, delivery_days, delivery_delay_days,
                is_late, purchase_timestamp, delivered_timestamp
            )
            VALUES (
                :order_id, :order_item_id,
                :customer_key, :product_key, :seller_key, :date_key,
                :order_status, :payment_type, :payment_installments,
                :price, :freight_value, :total_revenue, :payment_value,
                :review_score, :delivery_days, :delivery_delay_days,
                :is_late, :purchase_timestamp, :delivered_timestamp
            )
            ON CONFLICT (order_id, order_item_id) DO NOTHING
        """)

        rows_inserted = 0
        total_rows = len(self.fact_df)

        with self.engine.connect() as conn:
            for i, (_, row) in enumerate(self.fact_df.iterrows()):
                result = conn.execute(query, {
                    "order_id":              row["order_id"],
                    "order_item_id":         int(row["order_item_id"]),
                    "customer_key":          int(row["customer_key"]),
                    "product_key":           int(row["product_key"]),
                    "seller_key":            int(row["seller_key"]),
                    "date_key":              int(row["date_key"]),
                    "order_status":          row["order_status"],
                    "payment_type":          row["payment_type"],
                    "payment_installments":  int(row["payment_installments"]) if not pd.isna(row["payment_installments"]) else 0,
                    "price":                 self._safe_float(row["price"]),
                    "freight_value":         self._safe_float(row["freight_value"]),
                    "total_revenue":         self._safe_float(row["total_revenue"]),
                    "payment_value":         self._safe_float(row["payment_value"]),
                    "review_score":          self._safe_float(row["review_score"]),
                    "delivery_days":         self._safe_float(row["delivery_days"]),
                    "delivery_delay_days":   self._safe_float(row["delivery_delay_days"]),
                    "is_late":               bool(row["is_late"]) if not pd.isna(row["is_late"]) else False,
                    "purchase_timestamp":    self._safe(row["purchase_timestamp"]),
                    "delivered_timestamp":   self._safe(row["delivered_timestamp"])
                })
                rows_inserted += result.rowcount

                # Batch commit + progress log
                if (i + 1) % batch_size == 0:
                    conn.commit()
                    pct = (i + 1) / total_rows * 100
                    print(f"    Progress: {i + 1:,}/{total_rows:,}  ({pct:.1f}%)")

            # Final commit for remaining rows
            conn.commit()

        print(f"\n  Total inserted: {rows_inserted:,} rows into fact_orders")
        self.rows_inserted = rows_inserted

        return self

    # ──────────────────────────────────────────────
    # Step 4 — Verify
    # ──────────────────────────────────────────────

    def verify(self):
        """
        Confirm row counts and quick stats from fact_orders.
        """
        print("\n" + "=" * 55)
        print("VERIFICATION — fact_orders")
        print("=" * 55)

        with self.engine.connect() as conn:
            # Total rows
            r = conn.execute(text(
                "SELECT COUNT(*) FROM fact_orders"
            )).fetchone()
            print(f"\n  Total rows:        {r[0]:,}")

            # Revenue stats
            r = conn.execute(text(
                "SELECT SUM(total_revenue), AVG(total_revenue) FROM fact_orders"
            )).fetchone()
            print(f"  Total revenue:     R$ {r[0]:,.2f}")
            print(f"  Avg order value:   R$ {r[1]:,.2f}")

            # Unique orders
            r = conn.execute(text(
                "SELECT COUNT(DISTINCT order_id) FROM fact_orders"
            )).fetchone()
            print(f"  Unique orders:     {r[0]:,}")

            # Review score distribution
            r = conn.execute(text(
                "SELECT AVG(review_score), AVG(delivery_days) FROM fact_orders"
            )).fetchone()
            print(f"  Avg review score:  {r[0]:.2f}")
            print(f"  Avg delivery days: {r[1]:.1f}")

            # FK integrity check
            r = conn.execute(text("""
                SELECT
                    (SELECT COUNT(*) FROM fact_orders f
                     WHERE NOT EXISTS (
                         SELECT 1 FROM dim_customers d
                         WHERE d.customer_key = f.customer_key
                     )) AS orphan_customers,
                    (SELECT COUNT(*) FROM fact_orders f
                     WHERE NOT EXISTS (
                         SELECT 1 FROM dim_products d
                         WHERE d.product_key = f.product_key
                     )) AS orphan_products,
                    (SELECT COUNT(*) FROM fact_orders f
                     WHERE NOT EXISTS (
                         SELECT 1 FROM dim_sellers d
                         WHERE d.seller_key = f.seller_key
                     )) AS orphan_sellers,
                    (SELECT COUNT(*) FROM fact_orders f
                     WHERE NOT EXISTS (
                         SELECT 1 FROM dim_date d
                         WHERE d.date_key = f.date_key
                     )) AS orphan_dates
            """)).fetchone()

            print(f"\n  FK integrity check:")
            print(f"    Orphan customer keys:  {r[0]}")
            print(f"    Orphan product keys:   {r[1]}")
            print(f"    Orphan seller keys:    {r[2]}")
            print(f"    Orphan date keys:      {r[3]}")

            if all(v == 0 for v in r):
                print("\n  ✅ All foreign keys are valid!")
            else:
                print("\n  ⚠️  Some orphan keys found — investigate!")

        print("\n" + "=" * 55)
        print("fact_orders loaded successfully")
        print("Ready for Part 6 — business analysis")
        print("=" * 55)

    # ──────────────────────────────────────────────
    # run() — execute all steps
    # ──────────────────────────────────────────────

    def run(self):
        """Run the full fact loading pipeline."""

        print("=" * 55)
        print("PART 5 — LOADING FACT_ORDERS TABLE")
        print("=" * 55)

        self.load_lookups()
        self.build_fact_df()
        self.insert_facts(batch_size=500)
        self.verify()

        return self


if __name__ == "__main__":
    # Reuse your existing pipeline to get master DataFrame
    explore = DataExplore("data")
    cleaner = Data_cleaner(exp=explore)
    master_df = cleaner.run()

    # Load facts
    fact_loader = FactLoader(master_df)
    fact_loader.run()
