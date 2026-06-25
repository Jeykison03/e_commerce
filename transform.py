import pandas as pd
import numpy as np
from sqlalchemy import text
from database import get_engine
from analyse import BusinessAnalyser


class GoldTransformer:
    def __init__(self, analyser):
        self.engine   = get_engine()
        self.analyser = analyser
        self.df       = analyser.df   # the full star schema DataFrame

    # ──────────────────────────────────────────────
    # Helper — truncate + insert into a gold table
    # ──────────────────────────────────────────────

    def _write_gold_table(self, df, table_name):
        """
        Truncate existing rows and insert fresh aggregation.
        Gold tables are small (< 1000 rows) so full reload is fast.
        """
        with self.engine.connect() as conn:
            conn.execute(text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY"))
            conn.commit()

        df.to_sql(
            table_name,
            self.engine,
            if_exists="append",   # table already exists, just add rows
            index=False,
            method="multi"        # batch insert
        )

        print(f"  ✅ {table_name:35s} → {len(df):,} rows written")

    # ──────────────────────────────────────────────
    # Gold 1 — Monthly Revenue
    # ──────────────────────────────────────────────

    def gold_monthly_revenue(self):
        """
        Aggregated monthly revenue with order counts and delivery metrics.
        Matches: gold_monthly_revenue table schema.
        """
        print("\nGold 1 — gold_monthly_revenue")
        print("-" * 50)

        df = self.df.copy()

        monthly = (
            df.groupby(["purchase_year", "purchase_month"])
            .agg(
                total_revenue   = ("total_revenue",  "sum"),
                total_orders    = ("order_id",       "nunique"),
                total_items     = ("order_item_key", "count"),
                avg_review_score = ("review_score",  "mean"),
                late_deliveries = ("is_late",         "sum"),
            )
            .reset_index()
            .sort_values(["purchase_year", "purchase_month"])
        )

        # avg order value
        monthly["avg_order_value"] = (
            monthly["total_revenue"] / monthly["total_orders"]
        ).round(2)

        # on-time rate
        monthly["on_time_rate"] = (
            (1 - monthly["late_deliveries"] / monthly["total_items"]) * 100
        ).round(2)

        # get month_name from dim_date
        month_map = (
            self.df[["purchase_month", "month_name"]]
            .drop_duplicates()
            .set_index("purchase_month")["month_name"]
        )
        monthly["month_name"] = monthly["purchase_month"].map(month_map)

        # round
        monthly["total_revenue"]    = monthly["total_revenue"].round(2)
        monthly["avg_review_score"] = monthly["avg_review_score"].round(2)
        monthly["late_deliveries"]  = monthly["late_deliveries"].astype(int)

        # select columns matching the gold table schema
        gold = monthly[[
            "purchase_year", "purchase_month", "month_name",
            "total_revenue", "total_orders", "total_items",
            "avg_order_value", "avg_review_score",
            "late_deliveries", "on_time_rate"
        ]].copy()

        gold = gold.rename(columns={
            "purchase_year":  "year",
            "purchase_month": "month"
        })

        self._write_gold_table(gold, "gold_monthly_revenue")
        return self

    # ──────────────────────────────────────────────
    # Gold 2 — Category Performance
    # ──────────────────────────────────────────────

    def gold_category_performance(self):
        """
        Revenue, orders, reviews, delivery per product category.
        Matches: gold_category_performance table schema.
        """
        print("\nGold 2 — gold_category_performance")
        print("-" * 50)

        df = self.df.copy()

        cats = (
            df.groupby("product_category")
            .agg(
                total_revenue    = ("total_revenue",  "sum"),
                total_orders     = ("order_id",       "nunique"),
                avg_review_score = ("review_score",   "mean"),
                avg_delivery_days = ("delivery_days",  "mean"),
                late_count       = ("is_late",         "sum"),
                total_sellers    = ("seller_id",       "nunique")
            )
            .reset_index()
            .sort_values("total_revenue", ascending=False)
        )

        cats["avg_order_value"] = (
            cats["total_revenue"] / cats["total_orders"]
        ).round(2)

        cats["late_rate"] = (
            cats["late_count"] / cats["total_orders"] * 100
        ).round(2)

        # round
        cats["total_revenue"]     = cats["total_revenue"].round(2)
        cats["avg_review_score"]  = cats["avg_review_score"].round(2)
        cats["avg_delivery_days"] = cats["avg_delivery_days"].round(2)

        gold = cats[[
            "product_category", "total_revenue", "total_orders",
            "avg_order_value", "avg_review_score", "avg_delivery_days",
            "late_rate", "total_sellers"
        ]]

        self._write_gold_table(gold, "gold_category_performance")
        return self

    # ──────────────────────────────────────────────
    # Gold 3 — Seller Performance
    # ──────────────────────────────────────────────

    def gold_seller_performance(self):
        """
        Revenue, orders, reviews, delivery per seller.
        Matches: gold_seller_performance table schema.
        """
        print("\nGold 3 — gold_seller_performance")
        print("-" * 50)

        df = self.df.copy()

        sellers = (
            df.groupby(["seller_id", "seller_state", "seller_city"])
            .agg(
                total_revenue     = ("total_revenue",  "sum"),
                total_orders      = ("order_id",       "nunique"),
                avg_review_score  = ("review_score",   "mean"),
                avg_delivery_days = ("delivery_days",   "mean"),
                late_count        = ("is_late",          "sum"),
            )
            .reset_index()
            .sort_values("total_revenue", ascending=False)
        )

        sellers["late_rate"] = (
            sellers["late_count"] / sellers["total_orders"] * 100
        ).round(2)

        # Top category per seller
        top_cat = (
            df.groupby(["seller_id", "product_category"])
            .agg(cat_revenue=("total_revenue", "sum"))
            .reset_index()
            .sort_values("cat_revenue", ascending=False)
            .drop_duplicates(subset="seller_id", keep="first")
            [["seller_id", "product_category"]]
            .rename(columns={"product_category": "top_category"})
        )

        sellers = sellers.merge(top_cat, on="seller_id", how="left")
        sellers["top_category"] = sellers["top_category"].fillna("unknown")

        # round
        sellers["total_revenue"]     = sellers["total_revenue"].round(2)
        sellers["avg_review_score"]  = sellers["avg_review_score"].round(2)
        sellers["avg_delivery_days"] = sellers["avg_delivery_days"].round(2)

        gold = sellers[[
            "seller_id", "seller_state", "seller_city",
            "total_revenue", "total_orders", "avg_review_score",
            "avg_delivery_days", "late_rate", "top_category"
        ]]

        self._write_gold_table(gold, "gold_seller_performance")
        return self

    # ──────────────────────────────────────────────
    # Gold 4 — Customer RFM Segments
    # ──────────────────────────────────────────────

    def gold_customer_segments(self):
        """
        RFM segmentation: Recency, Frequency, Monetary per customer.
        Matches: gold_customer_segments table schema.
        """
        print("\nGold 4 — gold_customer_segments")
        print("-" * 50)

        df = self.df.copy()

        # Reference date = latest order date + 1 day
        df["purchase_date"] = pd.to_datetime(df["purchase_date"])
        ref_date = df["purchase_date"].max() + pd.Timedelta(days=1)

        rfm = (
            df.groupby(["customer_id", "customer_state", "customer_city"])
            .agg(
                last_order_date = ("purchase_date",   "max"),
                frequency       = ("order_id",         "nunique"),
                monetary        = ("total_revenue",    "sum"),
            )
            .reset_index()
        )

        # Recency = days since last order
        rfm["recency_days"] = (
            ref_date - rfm["last_order_date"]
        ).dt.days

        # Convert last_order_date to date for DB
        rfm["last_order_date"] = rfm["last_order_date"].dt.date

        # RFM scores 1-5 using quantiles (5 = best)
        # Recency: lower is better → reverse labels
        rfm["recency_score"] = pd.qcut(
            rfm["recency_days"],
            q=5,
            labels=[5, 4, 3, 2, 1],   # low recency = high score
            duplicates="drop"
        ).astype(int)

        # Frequency: higher is better
        rfm["frequency_score"] = pd.qcut(
            rfm["frequency"].rank(method="first"),
            q=5,
            labels=[1, 2, 3, 4, 5],
            duplicates="drop"
        ).astype(int)

        # Monetary: higher is better
        rfm["monetary_score"] = pd.qcut(
            rfm["monetary"].rank(method="first"),
            q=5,
            labels=[1, 2, 3, 4, 5],
            duplicates="drop"
        ).astype(int)

        # Combined RFM score
        rfm["rfm_score"] = (
            rfm["recency_score"] +
            rfm["frequency_score"] +
            rfm["monetary_score"]
        )

        # Customer segment labels based on RFM score
        def segment(score):
            if score >= 13:
                return "Champion"
            elif score >= 10:
                return "Loyal"
            elif score >= 7:
                return "Potential"
            elif score >= 5:
                return "At Risk"
            else:
                return "Lost"

        rfm["customer_segment"] = rfm["rfm_score"].apply(segment)

        # round monetary
        rfm["monetary"] = rfm["monetary"].round(2)

        gold = rfm[[
            "customer_id", "customer_state", "customer_city",
            "recency_days", "frequency", "monetary",
            "recency_score", "frequency_score", "monetary_score",
            "rfm_score", "customer_segment", "last_order_date"
        ]]

        self._write_gold_table(gold, "gold_customer_segments")

        # Print segment summary
        seg_summary = (
            gold.groupby("customer_segment")
            .agg(
                count    = ("customer_id", "count"),
                avg_monetary = ("monetary", "mean")
            )
            .reset_index()
            .sort_values("count", ascending=False)
        )
        print("\n  Segment summary:")
        print(seg_summary.to_string(index=False))

        return self

    # ──────────────────────────────────────────────
    # Verify all gold tables
    # ──────────────────────────────────────────────

    def verify(self):
        """Confirm row counts for all gold tables."""
        print("\n" + "=" * 55)
        print("VERIFICATION — Gold Tables")
        print("=" * 55)

        tables = [
            "gold_monthly_revenue",
            "gold_category_performance",
            "gold_seller_performance",
            "gold_customer_segments"
        ]

        with self.engine.connect() as conn:
            for t in tables:
                r = conn.execute(text(
                    f"SELECT COUNT(*) FROM {t}"
                )).fetchone()
                print(f"  {t:35s} → {r[0]:,} rows")

        print("\n" + "=" * 55)
        print("All 4 Gold tables written successfully!")
        print("Ready for Part 8 — SQL analytics")
        print("=" * 55)

    # ──────────────────────────────────────────────
    # run() — execute full pipeline
    # ──────────────────────────────────────────────

    def run(self):
        """Run the full Gold layer transformation."""

        print("=" * 55)
        print("PART 7 — GOLD AGGREGATION TABLES")
        print("=" * 55)

        self.gold_monthly_revenue()
        self.gold_category_performance()
        self.gold_seller_performance()
        self.gold_customer_segments()
        self.verify()

        return self


if __name__ == "__main__":
    # Run Part 6 first to get the star schema DataFrame
    analyser = BusinessAnalyser()
    analyser.run()

    # Then transform to gold tables
    transformer = GoldTransformer(analyser)
    transformer.run()
