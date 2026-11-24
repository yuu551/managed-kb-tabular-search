"""質問の正解を pandas で出す"""

import pandas as pd

sales = pd.read_csv("data/sales_2026h1.csv", encoding="utf-8-sig", parse_dates=["日付"])
stores = pd.read_excel("data/stores.xlsx", sheet_name="店舗一覧", parse_dates=["開店日"])
sep = sales[sales["日付"].dt.strftime("%Y-%m") == "2026-09"]

print("行数:", len(sales), " 9月の行数:", len(sep))

# 質問A: 2026年9月の金額（区分を問わず）の店舗別合計
by_store = sep.groupby("店舗コード")["金額"].sum().sort_values(ascending=False)
print("\n[A] 9月の店舗別合計（区分を問わず）")
print(by_store.to_string())

# 質問B: 2026年9月の既存店の純売上を地域別に
first_day = pd.Timestamp("2026-09-01")
existing = stores[stores["開店日"] <= first_day - pd.DateOffset(months=12)]
net = sep[sep["区分"].isin(["通常", "返品"])]
net = net[net["店舗コード"].isin(existing["店舗コード"])]
net = net.merge(stores[["店舗コード", "地域"]], on="店舗コード")
print("\n[B] 既存店:", ", ".join(existing["店舗コード"]))
print(net.groupby("地域")["金額"].sum().to_string())
print("合計", net["金額"].sum())

# 参考: ルールを使わずに素朴に合計した場合
naive = sep.merge(stores[["店舗コード", "地域"]], on="店舗コード").groupby("地域")["金額"].sum()
print("\n[B参考] 全店・全区分の地域別合計")
print(naive.to_string())
