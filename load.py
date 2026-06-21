import os
import pandas as pd 
from datetime  import date, timedelta
from sqlalchemy import text
from database import get_engine
from explore import DataExplore



DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

class Dimension:
    def __init__(self,exp):
        self.engine = get_engine()
        self.raw = exp.load_all()

    def load_dim_date(self,start_year=2016, end_year=2018):
        print("\nGenerating dim_date...")
 
        start_date = date(start_year, 1, 1)
        end_date   = date(end_year,  12, 31)
 
        rows   = []
        cursor = start_date

        while cursor <= end_date:
            date_key = int(cursor.strftime("%Y%m%d"))

            rows.append({
                "date_key":     date_key,
                "full_date":    cursor,
                "year":         cursor.year,
                "month":        cursor.month,
                "month_name":   cursor.strftime("%B"),       
                "quarter":      (cursor.month - 1) // 3 + 1, 
                "week_of_year": int(cursor.strftime("%W")),  
                "day_of_month": cursor.day,
                "day_of_week":  cursor.isoweekday(),         
                "weekday_name": cursor.strftime("%A"),      
                "is_weekend":   cursor.isoweekday() in (6, 7) 
            })
 
            cursor += timedelta(days=1)  
 
        df = pd.DataFrame(rows)
 
        print(f"  Generated {len(df):,} date rows "
              f"({start_year}-01-01 to {end_year}-12-31)")
 
        rows_inserted = self.insert_dim_date(df)
        print(f"  Inserted: {rows_inserted:,} rows into dim_date")
 
        return df

    def insert_dim_date(self,df):
        rows_inserted = 0

        query = text("""
            INSERT INTO dim_date (
                date_key, full_date, year, month, month_name,
                quarter, week_of_year, day_of_month,
                day_of_week, weekday_name, is_weekend
            )
            VALUES (
                :date_key, :full_date, :year, :month, :month_name,
                :quarter, :week_of_year, :day_of_month,
                :day_of_week, :weekday_name, :is_weekend
            )
            ON CONFLICT (date_key) DO NOTHING
        """)

        with self.engine.connect() as conn:
            for _,row in df.iterrows():
                result = conn.execute(query, {
                    "date_key":     int(row["date_key"]),
                    "full_date":    row["full_date"],
                    "year":         int(row["year"]),
                    "month":        int(row["month"]),
                    "month_name":   row["month_name"],
                    "quarter":      int(row["quarter"]),
                    "week_of_year": int(row["week_of_year"]),
                    "day_of_month": int(row["day_of_month"]),
                    "day_of_week":  int(row["day_of_week"]),
                    "weekday_name": row["weekday_name"],
                    "is_weekend":   bool(row["is_weekend"])
                })
                rows_inserted += result.rowcount
            conn.commit()
 
        return rows_inserted
    

    def load_dim_customer(self):
        path = os.path.join(DATA_DIR, "olist_customers_dataset.csv")
        df   = pd.read_csv(path)
 
        print(f"  Raw rows in CSV:      {len(df):,}")
 
        
        df = df.drop_duplicates(subset="customer_id", keep="first")
 
        print(f"  After deduplication:  {len(df):,} unique customers")
 
        
        df = df.rename(columns={
            "customer_zip_code_prefix": "customer_zip"
        })
 
        
        df = df[[
            "customer_id",
            "customer_city",
            "customer_state",
            "customer_zip"
        ]]
 
        
        df["customer_city"]  = df["customer_city"].str.title().str.strip()
        df["customer_state"] = df["customer_state"].str.upper().str.strip()
 
        
        df["customer_city"]  = df["customer_city"].fillna("unknown")
        df["customer_state"] = df["customer_state"].fillna("unknown")
        df["customer_zip"]   = df["customer_zip"].astype(str).str.strip()
 
        rows_inserted = self.insert_customers(df)
        print(f"  Inserted: {rows_inserted:,} rows into dim_customers")
 
        return df
    

    def insert_customers(self,df):
        rows_inserted = 0
 
        query = text("""
            INSERT INTO dim_customers
                (customer_id, customer_city, customer_state, customer_zip)
            VALUES
                (:customer_id, :customer_city, :customer_state, :customer_zip)
            ON CONFLICT (customer_id) DO NOTHING
        """)
        # MySQL: INSERT IGNORE INTO dim_customers (...)
 
        with self.engine.connect() as conn:
            for _, row in df.iterrows():
                result = conn.execute(query, {
                    "customer_id":    row["customer_id"],
                    "customer_city":  row["customer_city"],
                    "customer_state": row["customer_state"],
                    "customer_zip":   row["customer_zip"]
                })
                rows_inserted += result.rowcount
            conn.commit()
 
        return rows_inserted
    
    def load_dim_products(self):
        
        print("\nLoading dim_products...")
 
        
        products_path = os.path.join(DATA_DIR, "olist_products_dataset.csv")
        products_df   = pd.read_csv(products_path)
 
        print(f"  Raw rows in CSV:  {len(products_df):,}")
 
        
        cat_path = os.path.join(
            DATA_DIR, "product_category_name_translation.csv"
        )
        cat_df = pd.read_csv(cat_path)
 
        
        products_df = products_df.merge(
            cat_df,
            on  = "product_category_name",
            how = "left"     
        )
 
        
        products_df = products_df.rename(columns={
            "product_category_name_english": "product_category"
        })
 
        
        products_df = products_df.drop_duplicates(
            subset="product_id", keep="first"
        )
        print(f"  Unique products:  {len(products_df):,}")
 
        
        df = products_df[[
            "product_id",
            "product_category",
            "product_weight_g",
            "product_length_cm",
            "product_height_cm",
            "product_width_cm"
        ]].copy()
 
        
        df["product_volume_cm3"] = (
            df["product_length_cm"]
            * df["product_height_cm"]
            * df["product_width_cm"]
        ).round(2)
 
        
        for col in ["product_weight_g", "product_length_cm",
                    "product_height_cm", "product_width_cm",
                    "product_volume_cm3"]:
            df[col] = df[col].fillna(df[col].median())
 
        df["product_category"] = (
            df["product_category"]
            .fillna(products_df["product_category_name"])
            .fillna("unknown")
            .str.replace("_", " ")
            .str.title()
            .str.strip()
        )
 
        rows_inserted = self._insert_products(df)
        print(f"  Inserted: {rows_inserted:,} rows into dim_products")
 
        return df 

    def _insert_products(self, df):
 
        rows_inserted = 0
 
        query = text("""
            INSERT INTO dim_products (
                product_id, product_category,
                product_weight_g, product_length_cm,
                product_height_cm, product_width_cm,
                product_volume_cm3
            )
            VALUES (
                :product_id, :product_category,
                :weight, :length,
                :height, :width,
                :volume
            )
            ON CONFLICT (product_id) DO NOTHING
        """)
        
 
        with self.engine.connect() as conn:
            for _, row in df.iterrows():
                result = conn.execute(query, {
                    "product_id":       row["product_id"],
                    "product_category": row["product_category"],
                    "weight":           float(row["product_weight_g"]),
                    "length":           float(row["product_length_cm"]),
                    "height":           float(row["product_height_cm"]),
                    "width":            float(row["product_width_cm"]),
                    "volume":           float(row["product_volume_cm3"])
                })
                rows_inserted += result.rowcount
            conn.commit()
 
        return rows_inserted
    
    def load_dim_sellers(self):
        
 
        print("\nLoading dim_sellers...")
 
        path = os.path.join(DATA_DIR, "olist_sellers_dataset.csv")
        df   = pd.read_csv(path)
 
        print(f"  Raw rows in CSV:  {len(df):,}")
 
        
        df = df.drop_duplicates(subset="seller_id", keep="first")
        print(f"  Unique sellers:   {len(df):,}")
 
       
        df = df.rename(columns={
            "seller_zip_code_prefix": "seller_zip"
        })
 
        
        df = df[[
            "seller_id",
            "seller_city",
            "seller_state",
            "seller_zip"
        ]].copy()
 
        
        df["seller_city"]  = df["seller_city"].str.title().str.strip()
        df["seller_state"] = df["seller_state"].str.upper().str.strip()
        df["seller_city"]  = df["seller_city"].fillna("unknown")
        df["seller_state"] = df["seller_state"].fillna("unknown")
        df["seller_zip"]   = df["seller_zip"].astype(str).str.strip()
 
        rows_inserted = self._insert_sellers(df)
        print(f"  Inserted: {rows_inserted:,} rows into dim_sellers")
 
        return df
    

    def _insert_sellers(self, df):
 
        rows_inserted = 0
 
        query = text("""
            INSERT INTO dim_sellers
                (seller_id, seller_city, seller_state, seller_zip)
            VALUES
                (:seller_id, :seller_city, :seller_state, :seller_zip)
            ON CONFLICT (seller_id) DO NOTHING
        """)
        
 
        with self.engine.connect() as conn:
            for _, row in df.iterrows():
                result = conn.execute(query, {
                    "seller_id":    row["seller_id"],
                    "seller_city":  row["seller_city"],
                    "seller_state": row["seller_state"],
                    "seller_zip":   row["seller_zip"]
                })
                rows_inserted += result.rowcount
            conn.commit()
 
        return rows_inserted
    
    def verify(self):
        """
        After loading all dimensions, run a quick check.
        Confirm row counts and sample data for each table.
        """
 
        print("\n" + "=" * 55)
        print("VERIFICATION — dimension tables")
        print("=" * 55)
 
        tables = {
            "dim_date":      "SELECT COUNT(*), MIN(full_date), MAX(full_date) FROM dim_date",
            "dim_customers": "SELECT COUNT(*), COUNT(DISTINCT customer_state) FROM dim_customers",
            "dim_products":  "SELECT COUNT(*), COUNT(DISTINCT product_category) FROM dim_products",
            "dim_sellers":   "SELECT COUNT(*), COUNT(DISTINCT seller_state) FROM dim_sellers"
        }
 
        with self.engine.connect() as conn:
 
            
            r = conn.execute(text(
                "SELECT COUNT(*), MIN(full_date), MAX(full_date) FROM dim_date"
            )).fetchone()
            print(f"\n  dim_date")
            print(f"    Rows:       {r[0]:,}")
            print(f"    Date range: {r[1]} → {r[2]}")
 
            
            r = conn.execute(text(
                "SELECT COUNT(*), COUNT(DISTINCT customer_state) FROM dim_customers"
            )).fetchone()
            print(f"\n  dim_customers")
            print(f"    Rows:   {r[0]:,}")
            print(f"    States: {r[1]}")
 
        
            r = conn.execute(text(
                "SELECT COUNT(*), COUNT(DISTINCT product_category) FROM dim_products"
            )).fetchone()
            print(f"\n  dim_products")
            print(f"    Rows:       {r[0]:,}")
            print(f"    Categories: {r[1]}")
 
            
            r = conn.execute(text(
                "SELECT COUNT(*), COUNT(DISTINCT seller_state) FROM dim_sellers"
            )).fetchone()
            print(f"\n  dim_sellers")
            print(f"    Rows:   {r[0]:,}")
            print(f"    States: {r[1]}")
 
        print("\n" + "=" * 55)
        print("All 4 dimension tables loaded successfully")
        print("Ready for Part 5 — loading fact_orders")
        print("=" * 55)


    def run(self):
        """Run all 4 dimension loads in correct order."""
 
        print("=" * 55)
        print("PART 4 — LOADING DIMENSION TABLES")
        print("=" * 55)
 
        
        self.load_dim_date(start_year=2016, end_year=2018)
 
        
        self.load_dim_customer()
        self.load_dim_products()
        self.load_dim_sellers()
 
        
        self.verify()

if __name__ == "__main__":
    explore = DataExplore("data")
    loader = Dimension(explore)
    loader.run()
 