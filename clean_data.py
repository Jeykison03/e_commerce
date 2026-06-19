import os 
import pandas as pd
import numpy as np
from explore import DataExplore

class Data_cleaner():
    def __init__(self,exp):
        self.raw = exp.load_all()
        self.master = None


    def merge_all(self):
        df =self.raw["orders"].merge(
            self.raw["customers"][[
                "customer_id",
                "customer_city",
                "customer_state",
                "customer_zip_code_prefix"
            ]],
            on  = "customer_id",
            how = "inner"       
        )


        df = df.merge(
            self.raw["order_items"][[
                "order_id",
                "order_item_id",
                "product_id",
                "seller_id",
                "price",
                "freight_value"
            ]],
            on  = "order_id",
            how = "inner"       # every order must have at least one item
        )


        df = df.merge(
            self.raw["products"][[
                "product_id",
                "product_category_name",
                "product_weight_g",
                "product_length_cm",
                "product_height_cm",
                "product_width_cm"
            ]],
            on  = "product_id",
            how = "inner"
        )

        df = df.merge(
            self.raw["category_translation"][[
                "product_category_name",
                "product_category_name_english"
            ]],
            on = "product_category_name",
            how = "left"

        )

        df = df.merge(
            self.raw["sellers"][[
                "seller_id",
                "seller_city",
                "seller_state",
                "seller_zip_code_prefix"
            ]],
            on = "seller_id",
            how = "inner"
        )

        reviews_clean = (
            self.raw["reviews"]
            .sort_values("review_creation_date", ascending=False)
            .drop_duplicates(subset="order_id", keep="first")
            [["order_id", "review_score", "review_creation_date"]]
        )
        df = df.merge(
            reviews_clean,
            on  = "order_id",
            how = "left"
        )

        payments_clean = (
            self.raw["payments"]
            .sort_values("payment_value", ascending=False)
            .drop_duplicates(subset="order_id", keep="first")
            [["order_id", "payment_type", "payment_installments", "payment_value"]]
        )
        df = df.merge(
            payments_clean,
            on  = "order_id",
            how = "left"
        )
        print(f"\nMerge complete. Master shape: {df.shape}")
        self.master = df
        return self
    
    def clean_orders(self):
        df = self.raw["orders"].copy()

        date_cols = [
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date"
        ]

        for col in date_cols:
            if col in self.master.columns:
                self.master[col] = pd.to_datetime(
                    self.master[col],
                    errors="coerce"     
                )
               
 
        return self
    
    def add_calculated_columns(self):
        self.master["delivery_days"] = (
            self.master["order_delivered_customer_date"]
            - self.master["order_purchase_timestamp"]
        ).dt.days
        
        self.master["delivery_delay_days"] = (
            self.master["order_delivered_customer_date"]
            - self.master["order_estimated_delivery_date"]
        ).dt.days

        self.master["purchase_year"]    = self.master["order_purchase_timestamp"].dt.year
        self.master["purchase_month"]   = self.master["order_purchase_timestamp"].dt.month
        self.master["purchase_quarter"] = self.master["order_purchase_timestamp"].dt.quarter
        self.master["purchase_weekday"] = self.master["order_purchase_timestamp"].dt.day_name()
        self.master["purchase_date"]    = self.master["order_purchase_timestamp"].dt.date
        

        self.master["product_volume_cm3"] = (
            self.master["product_length_cm"]
            * self.master["product_height_cm"]
            * self.master["product_width_cm"]
        )

        self.master["is_late"] = (
            self.master["delivery_delay_days"] > 0
        ).astype(int)     # 1 = late, 0 = on time or early
        print("  is_late = 1 if delivery_delay_days > 0")
 
        return self
    

    def filter_delivery(self):
        before = len(self.master)
        self.master = self.master[
            self.master["order_status"] == "delivered"
        ].copy()
        after = len(self.master)

        print(f"\nFiltered to delivered orders only:")
        print(f"  Before: {before:,} rows")
        print(f"  After:  {after:,} rows")
        print(f"  Removed: {before - after:,} rows (cancelled, shipped etc.)")

        return self
    

    def handle_nulls(self):
        null_before = self.master["review_score"].isnull().sum()
        self.master["review_score"] = self.master["review_score"].fillna(0)
        print(f"  review_score:              {null_before:,} nulls → filled with 0 (no review)")
 
        
        null_before = self.master["product_category_name_english"].isnull().sum()
        self.master["product_category_name_english"] = (
            self.master["product_category_name_english"]
            .fillna(self.master["product_category_name"])
            .fillna("unknown")     
        )
        print(f"  product_category_english:  {null_before:,} nulls → filled with Portuguese name")
 
        
        null_before = self.master["delivery_days"].isnull().sum()
        median_days = self.master["delivery_days"].median()
        self.master["delivery_days"] = (
            self.master["delivery_days"].fillna(median_days)
        )
        print(f"  delivery_days:             {null_before:,} nulls → filled with median ({median_days:.0f} days)")
 
        
        null_before = self.master["delivery_delay_days"].isnull().sum()
        self.master["delivery_delay_days"] = (
            self.master["delivery_delay_days"].fillna(0)
        )
        print(f"  delivery_delay_days:       {null_before:,} nulls → filled with 0")
 
        
        null_before = self.master["payment_type"].isnull().sum()
        self.master["payment_type"] = self.master["payment_type"].fillna("unknown")
        print(f"  payment_type:              {null_before:,} nulls → filled with 'unknown'")
 
        
        for col in ["product_weight_g", "product_length_cm",
                    "product_height_cm",  "product_width_cm",
                    "product_volume_cm3"]:
            null_before = self.master[col].isnull().sum()
            if null_before > 0:
                median_val = self.master[col].median()
                self.master[col] = self.master[col].fillna(median_val)
                print(f"  {col:<35} {null_before:,} nulls → filled with median")
 
        return self

    def clean_type(self):
        numeric_cols = {
            "price":                float,
            "freight_value":        float,
            "total_revenue":        float,
            "payment_value":        float,
            "review_score":         float,
            "delivery_days":        float,
            "delivery_delay_days":  float,
            "product_weight_g":     float,
            "product_volume_cm3":   float,
            "payment_installments": float,
            "order_item_id":        int,
            "is_late":              int,
        }
 
        for col, dtype in numeric_cols.items():
            if col in self.master.columns:
                self.master[col] = pd.to_numeric(
                    self.master[col], errors="coerce"
                ).astype(dtype)
 
        # rename for clarity
        self.master = self.master.rename(columns={
            "product_category_name_english": "product_category",
            "customer_zip_code_prefix":      "customer_zip",
            "seller_zip_code_prefix":        "seller_zip"
        })
 
        
 
        return self
    
    def remove_duplicate(self):
        before = len(self.master)
        self.master = self.master.drop_duplicates(
            subset=["order_id", "order_item_id"]
        ).reset_index(drop=True)
        after = len(self.master)
 
        print(f"\nDuplicate removal:")
        print(f"  Removed {before - after:,} duplicate rows")
 
        return self
    

    def print_summary(self):
        df = self.master
        print("\n" + "=" * 60)
        print("MASTER DATAFRAME — FINAL SUMMARY")
        print("=" * 60)
 
        print(f"\nShape: {df.shape[0]:,} rows × {df.shape[1]} columns")
 
        print("\nAll columns and types:")
        print("-" * 50)

        print(df)

    def run(self):
        """
        Run all cleaning steps in order.
        Returns the final clean master DataFrame.
        """
 
        print("=" * 60)
        print("PART 2 — DATA CLEANING PIPELINE")
        print("=" * 60)
 
        
        self.merge_all()
        self.clean_orders()
        self.add_calculated_columns()
        self.filter_delivery()
        self.handle_nulls()
        self.clean_type()
        self.remove_duplicate()
        self.print_summary()
 
        return self.master
    
if __name__ == "__main__":
    explore = DataExplore("data")
    cleaner = Data_cleaner(exp = explore)
    master_df = cleaner.run()
 
    
    output_path = os.path.join(
        os.path.dirname(__file__), "data", "master_clean.csv"
    )
    master_df.to_csv(output_path, index=False)
    print(f"\nSaved to: {output_path}")
    print("You can load this in Part 3+ with pd.read_csv('data/master_clean.csv')")
