import pandas as pd


def create_report(file_path):
    data = pd.read_csv(file_path)
    print(f"데이터 크기: {data.shape}")
    print(data.describe(include="all"))
    print("\n결측치")
    print(data.isna().sum())


create_report("sample.csv")
