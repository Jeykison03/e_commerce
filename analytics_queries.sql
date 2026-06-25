-- ============================================================
-- PART 8 — SQL ANALYTICS ON STAR SCHEMA
-- ============================================================
-- All queries run on fact_orders joined with dimension tables.
-- Demonstrates: RANK, SUM OVER, LAG, NTILE, AVG OVER, ROW_NUMBER
-- ============================================================


-- ──────────────────────────────────────────────
-- Query 1: RANK() — Product categories by monthly revenue
--          Which category grew fastest month to month?
-- ──────────────────────────────────────────────

SELECT
    d.year,
    d.month,
    d.month_name,
    p.product_category,
    SUM(f.total_revenue)                                     AS monthly_revenue,
    RANK() OVER (
        PARTITION BY d.year, d.month
        ORDER BY SUM(f.total_revenue) DESC
    )                                                        AS revenue_rank
FROM fact_orders      f
JOIN dim_products     p  ON f.product_key = p.product_key
JOIN dim_date         d  ON f.date_key    = d.date_key
GROUP BY d.year, d.month, d.month_name, p.product_category
ORDER BY d.year, d.month, revenue_rank;


-- ──────────────────────────────────────────────
-- Query 2: SUM() OVER — Running total revenue month by month
--          Cumulative revenue growth across the entire business
-- ──────────────────────────────────────────────

WITH monthly_totals AS (
    SELECT
        d.year,
        d.month,
        d.month_name,
        SUM(f.total_revenue)           AS monthly_revenue,
        COUNT(DISTINCT f.order_id)     AS monthly_orders
    FROM fact_orders  f
    JOIN dim_date     d  ON f.date_key = d.date_key
    GROUP BY d.year, d.month, d.month_name
)
SELECT
    year,
    month,
    month_name,
    monthly_revenue,
    monthly_orders,
    SUM(monthly_revenue) OVER (
        ORDER BY year, month
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )                                                        AS running_total_revenue,
    SUM(monthly_orders) OVER (
        ORDER BY year, month
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )                                                        AS running_total_orders
FROM monthly_totals
ORDER BY year, month;


-- ──────────────────────────────────────────────
-- Query 3: LAG() — Month-over-month revenue growth %
--          "This month vs last month — are we growing?"
-- ──────────────────────────────────────────────

WITH monthly_totals AS (
    SELECT
        d.year,
        d.month,
        d.month_name,
        SUM(f.total_revenue)           AS monthly_revenue,
        COUNT(DISTINCT f.order_id)     AS monthly_orders
    FROM fact_orders  f
    JOIN dim_date     d  ON f.date_key = d.date_key
    GROUP BY d.year, d.month, d.month_name
)
SELECT
    year,
    month,
    month_name,
    monthly_revenue,
    LAG(monthly_revenue) OVER (ORDER BY year, month)         AS prev_month_revenue,
    ROUND(
        (monthly_revenue - LAG(monthly_revenue) OVER (ORDER BY year, month))
        / NULLIF(LAG(monthly_revenue) OVER (ORDER BY year, month), 0)
        * 100,
        2
    )                                                        AS mom_growth_pct,
    monthly_orders,
    LAG(monthly_orders) OVER (ORDER BY year, month)          AS prev_month_orders
FROM monthly_totals
ORDER BY year, month;


-- ──────────────────────────────────────────────
-- Query 4: NTILE(4) — Split customers into revenue quartiles
--          Champion / High / Mid / Low value customers
-- ──────────────────────────────────────────────

WITH customer_revenue AS (
    SELECT
        c.customer_id,
        c.customer_state,
        c.customer_city,
        COUNT(DISTINCT f.order_id)       AS total_orders,
        SUM(f.total_revenue)             AS total_spent,
        AVG(f.review_score)              AS avg_review,
        AVG(f.delivery_days)             AS avg_delivery
    FROM fact_orders      f
    JOIN dim_customers    c  ON f.customer_key = c.customer_key
    GROUP BY c.customer_id, c.customer_state, c.customer_city
)
SELECT
    customer_id,
    customer_state,
    total_orders,
    ROUND(total_spent::numeric, 2)       AS total_spent,
    ROUND(avg_review::numeric, 2)        AS avg_review,
    NTILE(4) OVER (ORDER BY total_spent DESC)  AS revenue_quartile,
    CASE NTILE(4) OVER (ORDER BY total_spent DESC)
        WHEN 1 THEN 'Champion'
        WHEN 2 THEN 'High Value'
        WHEN 3 THEN 'Mid Value'
        WHEN 4 THEN 'Low Value'
    END                                  AS customer_tier
FROM customer_revenue
ORDER BY total_spent DESC;


-- ──────────────────────────────────────────────
-- Query 5: AVG() OVER — Rolling 3-month average revenue per category
--          Smooths out spikes, shows real trend direction
-- ──────────────────────────────────────────────

WITH category_monthly AS (
    SELECT
        p.product_category,
        d.year,
        d.month,
        SUM(f.total_revenue)                              AS monthly_revenue,
        COUNT(DISTINCT f.order_id)                        AS monthly_orders
    FROM fact_orders      f
    JOIN dim_products     p  ON f.product_key = p.product_key
    JOIN dim_date         d  ON f.date_key    = d.date_key
    GROUP BY p.product_category, d.year, d.month
)
SELECT
    product_category,
    year,
    month,
    monthly_revenue,
    ROUND(
        AVG(monthly_revenue) OVER (
            PARTITION BY product_category
            ORDER BY year, month
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        )::numeric,
        2
    )                                                     AS rolling_3m_avg_revenue,
    monthly_orders,
    ROUND(
        AVG(monthly_orders) OVER (
            PARTITION BY product_category
            ORDER BY year, month
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        )::numeric,
        1
    )                                                     AS rolling_3m_avg_orders
FROM category_monthly
ORDER BY product_category, year, month;


-- ──────────────────────────────────────────────
-- Query 6: ROW_NUMBER() — Rank sellers by revenue within each state
--          "Who is the #1 seller in São Paulo? In Rio?"
-- ──────────────────────────────────────────────

WITH seller_revenue AS (
    SELECT
        s.seller_id,
        s.seller_state,
        s.seller_city,
        COUNT(DISTINCT f.order_id)                        AS total_orders,
        SUM(f.total_revenue)                              AS total_revenue,
        ROUND(AVG(f.review_score)::numeric, 2)            AS avg_review,
        ROUND(AVG(f.delivery_days)::numeric, 1)           AS avg_delivery_days
    FROM fact_orders      f
    JOIN dim_sellers      s  ON f.seller_key = s.seller_key
    GROUP BY s.seller_id, s.seller_state, s.seller_city
)
SELECT
    seller_id,
    seller_state,
    seller_city,
    total_orders,
    ROUND(total_revenue::numeric, 2)                      AS total_revenue,
    avg_review,
    avg_delivery_days,
    ROW_NUMBER() OVER (
        PARTITION BY seller_state
        ORDER BY total_revenue DESC
    )                                                     AS state_rank
FROM seller_revenue
ORDER BY seller_state, state_rank;


-- ──────────────────────────────────────────────
-- BONUS Query 7: Category revenue growth rate using LAG
--                "Health & Beauty grew 45% in Q4 2017"
-- ──────────────────────────────────────────────

WITH quarterly_cats AS (
    SELECT
        p.product_category,
        d.year,
        d.quarter,
        SUM(f.total_revenue)                              AS q_revenue
    FROM fact_orders      f
    JOIN dim_products     p  ON f.product_key = p.product_key
    JOIN dim_date         d  ON f.date_key    = d.date_key
    GROUP BY p.product_category, d.year, d.quarter
),
with_growth AS (
    SELECT
        product_category,
        year,
        quarter,
        q_revenue,
        LAG(q_revenue) OVER (
            PARTITION BY product_category
            ORDER BY year, quarter
        )                                                 AS prev_q_revenue,
        ROUND(
            (q_revenue - LAG(q_revenue) OVER (
                PARTITION BY product_category
                ORDER BY year, quarter
            ))
            / NULLIF(LAG(q_revenue) OVER (
                PARTITION BY product_category
                ORDER BY year, quarter
            ), 0)
            * 100,
            2
        )                                                 AS qoq_growth_pct
    FROM quarterly_cats
)
SELECT *
FROM with_growth
WHERE qoq_growth_pct IS NOT NULL
ORDER BY qoq_growth_pct DESC
LIMIT 20;
