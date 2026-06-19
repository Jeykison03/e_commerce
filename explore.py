import pandas as pd
import os

FILES = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "category_translation": "product_category_name_translation.csv"
}


class DataExplore:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.dataframes = {}

    def load_all(self):
        for name, filename in FILES.items():
            path = os.path.join(self.data_dir, filename)

            if not os.path.exists(path):
                print(f"\n❌ MISSING FILE: {filename}")
                continue

            df = pd.read_csv(path)
            self.dataframes[name] = df

        return self.dataframes
    


        

    
    def check_all(self):
        for name, df in self.dataframes.items():
            print("\n" + "=" * 60)
            print(f"📁 FILE: {name}")
            print("=" * 60)

            
            print("\n📌 Columns:")
            print(df.columns.tolist())

            
            print("\n❌ Missing Values:")
            missing = df.isnull().sum()
            print(missing[missing > 0] if missing.sum() > 0 else "No missing values")

            
            print("\n🔢 Unique Values per Column:")
            for col in df.columns:
                print(f"{col}: {df[col].nunique()}")

            print("\n" + "-" * 60)

            

if __name__ == "__main__":
    explore = DataExplore("data")
    explore.load_all()
    for name, df in explore.dataframes.items():
        print(name)
    print(explore.dataframes["orders"].columns)

    #explore.check_all()
