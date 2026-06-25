import pandas as pd
from sqlalchemy import text
from database import get_engine


class BusinessAnalyser:
    def __init__(self):
        self.engine = get_engine()
        self.df     = None

    # ──────────────────────────────────────────────
    # Step 1 — Load star schema into one DataFrame
    # ──────────────────────────────────────────────

    def load_star_schema(self):
        """
        Read fact_orders joined with all 4 dimension tables.
        This is the full denormalised view for analysis.
        """
        print("\nStep 1 — Loading star schema from PostgreSQL")
        print("-" * 55)

        query = """
            SELECT
                f.order_item_key,
                f.order_id,
                f.order_item_id,
                f.order_status,
                f.payment_type,
                f.payment_installments,
                f.price,
                f.freight_value,
                f.total_revenue,
                f.payment_value,
                f.review_score,
                f.delivery_days,
                f.delivery_delay_days,
                f.is_late,
                f.purchase_timestamp,
                f.delivered_timestamp,

                c.customer_id,
                c.customer_city,
                c.customer_state,

                p.product_id,
                p.product_category,
                p.product_weight_g,
                p.product_volume_cm3,

                s.seller_id,
                s.seller_city,
                s.seller_state,

                d.full_date       AS purchase_date,
                d.year            AS purchase_year,
                d.month           AS purchase_month,
                d.month_name,
                d.quarter         AS purchase_quarter,
                d.weekday_name    AS purchase_weekday,
                d.is_weekend

            FROM fact_orders      f
            JOIN dim_customers    c ON f.customer_key = c.customer_key
            JOIN dim_products     p ON f.product_key  = p.product_key
            JOIN dim_sellers      s ON f.seller_key   = s.seller_key
            JOIN dim_date         d ON f.date_key     = d.date_key
        """

        with self.engine.connect() as conn:
            self.df = pd.read_sql(query, conn)

        print(f"  Loaded {len(self.df):,} rows × {self.df.shape[1]} columns")
        return self

    # ──────────────────────────────────────────────
    # Analysis 1 — Monthly revenue trend
    # ──────────────────────────────────────────────

    def monthly_revenue(self):
        """Monthly revenue — is the business growing?"""
        print("\n" + "=" * 55)
        print("ANALYSIS 1 — Monthly Revenue Trend")
        print("=" * 55)

        monthly = (
            self.df
            .groupby(["purchase_year", "purchase_month", "month_name"])
            .agg(
                total_revenue = ("total_revenue", "sum"),
                total_orders  = ("order_id",       "nunique"),
                total_items   = ("order_item_key", "count"),
                avg_review    = ("review_score",   "mean")
            )
            .reset_index()
            .sort_values(["purchase_year", "purchase_month"])
        )

        # Month-over-month growth
        monthly["mom_growth_%"] = (
            monthly["total_revenue"].pct_change() * 100
        ).round(2)

        print(monthly.to_string(index=False))

        self.monthly = monthly
        return self

    # ──────────────────────────────────────────────
    # Analysis 2 — Top 10 categories
    # ──────────────────────────────────────────────

    def top_categories(self):
        """Top 10 product categories by revenue and order count."""
        print("\n" + "=" * 55)
        print("ANALYSIS 2 — Top 10 Product Categories")
        print("=" * 55)

        cats = (
            self.df
            .groupby("product_category")
            .agg(
                total_revenue    = ("total_revenue",  "sum"),
                total_orders     = ("order_id",       "nunique"),
                avg_review       = ("review_score",   "mean"),
                avg_delivery     = ("delivery_days",  "mean")
            )
            .reset_index()
            .sort_values("total_revenue", ascending=False)
        )

        print("\n  By Revenue:")
        print(cats.head(10).to_string(index=False))

        print("\n  By Order Count:")
        by_orders = cats.sort_values("total_orders", ascending=False)
        print(by_orders.head(10).to_string(index=False))

        self.categories = cats
        return self

    # ──────────────────────────────────────────────
    # Analysis 3 — Delivery days by seller state
    # ──────────────────────────────────────────────

    def delivery_by_state(self):
        """Average delivery days by seller state — which regions are slow?"""
        print("\n" + "=" * 55)
        print("ANALYSIS 3 — Delivery Performance by Seller State")
        print("=" * 55)

        state = (
            self.df
            .groupby("seller_state")
            .agg(
                avg_delivery    = ("delivery_days",      "mean"),
                avg_delay       = ("delivery_delay_days", "mean"),
                late_count      = ("is_late",             "sum"),
                total_orders    = ("order_id",            "nunique"),
                total_revenue   = ("total_revenue",       "sum")
            )
            .reset_index()
        )
        state["late_rate_%"] = (
            state["late_count"] / state["total_orders"] * 100
        ).round(2)

        state = state.sort_values("avg_delivery", ascending=True)

        print("\n  Fastest delivery states (top 5):")
        print(state.head(5).to_string(index=False))

        print("\n  Slowest delivery states (bottom 5):")
        print(state.tail(5).to_string(index=False))

        self.delivery_states = state
        return self

    # ──────────────────────────────────────────────
    # Analysis 4 — Review score distribution
    # ──────────────────────────────────────────────

    def review_distribution(self):
        """Review score distribution — what % are 5 stars?"""
        print("\n" + "=" * 55)
        print("ANALYSIS 4 — Review Score Distribution")
        print("=" * 55)

        # Filter out 0 (no review submitted)
        reviewed = self.df[self.df["review_score"] > 0]

        dist = (
            reviewed
            .groupby("review_score")
            .agg(count=("order_id", "count"))
            .reset_index()
        )
        dist["percentage_%"] = (
            dist["count"] / dist["count"].sum() * 100
        ).round(2)

        print(dist.to_string(index=False))

        five_star = dist.loc[
            dist["review_score"] == 5, "percentage_%"
        ].values
        if len(five_star) > 0:
            print(f"\n  ⭐ 5-star rate: {five_star[0]:.1f}%")

        avg = reviewed["review_score"].mean()
        print(f"  📊 Average score: {avg:.2f}")

        return self

    # ──────────────────────────────────────────────
    # Analysis 5 — Peak ordering days and hours
    # ──────────────────────────────────────────────

    def peak_ordering_days(self):
        """Which day of week and hour gets the most orders?"""
        print("\n" + "=" * 55)
        print("ANALYSIS 5 — Peak Ordering Times")
        print("=" * 55)

        # By weekday
        df = self.df.copy()
        weekday_order = [
            "Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday"
        ]

        by_day = (
            df.groupby("purchase_weekday")
            .agg(
                total_orders  = ("order_id",      "nunique"),
                total_revenue = ("total_revenue",  "sum")
            )
            .reset_index()
        )
        by_day["purchase_weekday"] = pd.Categorical(
            by_day["purchase_weekday"],
            categories=weekday_order,
            ordered=True
        )
        by_day = by_day.sort_values("purchase_weekday")

        print("\n  Orders by Day of Week:")
        print(by_day.to_string(index=False))

        # By hour
        df["purchase_hour"] = pd.to_datetime(
            df["purchase_timestamp"]
        ).dt.hour

        by_hour = (
            df.groupby("purchase_hour")
            .agg(
                total_orders  = ("order_id",     "nunique"),
                total_revenue = ("total_revenue", "sum")
            )
            .reset_index()
            .sort_values("total_orders", ascending=False)
        )

        print("\n  Top 5 Peak Hours:")
        print(by_hour.head(5).to_string(index=False))

        return self

    # ──────────────────────────────────────────────
    # Analysis 6 — Revenue by payment type
    # ──────────────────────────────────────────────

    def revenue_by_payment(self):
        """Revenue by payment type: credit card vs boleto vs voucher."""
        print("\n" + "=" * 55)
        print("ANALYSIS 6 — Revenue by Payment Type")
        print("=" * 55)

        pay = (
            self.df
            .groupby("payment_type")
            .agg(
                total_revenue  = ("total_revenue",       "sum"),
                total_orders   = ("order_id",            "nunique"),
                avg_installments = ("payment_installments", "mean")
            )
            .reset_index()
            .sort_values("total_revenue", ascending=False)
        )
        pay["revenue_share_%"] = (
            pay["total_revenue"] / pay["total_revenue"].sum() * 100
        ).round(2)

        print(pay.to_string(index=False))

        return self

    # ──────────────────────────────────────────────
    # Analysis 7 — Customer repeat rate
    # ──────────────────────────────────────────────

    def customer_repeat_rate(self):
        """How many customers ordered more than once?"""
        print("\n" + "=" * 55)
        print("ANALYSIS 7 — Customer Repeat Rate")
        print("=" * 55)

        customer_orders = (
            self.df
            .groupby("customer_id")
            .agg(order_count=("order_id", "nunique"))
            .reset_index()
        )

        total_customers = len(customer_orders)
        one_time        = len(customer_orders[customer_orders["order_count"] == 1])
        repeat          = len(customer_orders[customer_orders["order_count"] > 1])
        repeat_rate     = repeat / total_customers * 100

        print(f"\n  Total unique customers:  {total_customers:,}")
        print(f"  One-time buyers:         {one_time:,}")
        print(f"  Repeat buyers:           {repeat:,}")
        print(f"  Repeat rate:             {repeat_rate:.2f}%")

        # Top repeat customers
        top_repeat = (
            customer_orders
            .sort_values("order_count", ascending=False)
            .head(10)
        )
        print("\n  Top 10 repeat customers:")
        print(top_repeat.to_string(index=False))

        return self

    # ──────────────────────────────────────────────
    # run() — execute all analyses
    # ──────────────────────────────────────────────

    def run(self):
        """Run all 7 business analyses."""

        print("=" * 55)
        print("PART 6 — BUSINESS ANALYSIS")
        print("=" * 55)

        self.load_star_schema()
        self.monthly_revenue()
        self.top_categories()
        self.delivery_by_state()
        self.review_distribution()
        self.peak_ordering_days()
        self.revenue_by_payment()
        self.customer_repeat_rate()

        print("\n" + "=" * 55)
        print("All 7 analyses complete!")
        print("Ready for Part 7 — Gold aggregation tables")
        print("=" * 55)

        return self


if __name__ == "__main__":
    analyser = BusinessAnalyser()
    analyser.run()
