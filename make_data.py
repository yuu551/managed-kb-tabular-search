"""架空の売上明細・店舗マスタ・集計ルールを作る"""

import random
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook

OUT = Path("data")
OUT.mkdir(exist_ok=True)
random.seed(20261124)

# 店舗コード, 店舗名, 地域, 開店日
STORES = [
    ("S001", "札幌店", "北海道・東北", date(2019, 4, 1)),
    ("S002", "仙台店", "北海道・東北", date(2021, 10, 1)),
    ("S003", "新宿店", "関東", date(2018, 6, 1)),
    ("S004", "横浜店", "関東", date(2025, 12, 1)),
    ("S005", "名古屋店", "中部", date(2020, 3, 1)),
    ("S006", "京都店", "近畿", date(2025, 9, 15)),
    ("S007", "大阪店", "近畿", date(2017, 11, 1)),
    ("S008", "神戸店", "近畿", date(2022, 5, 1)),
    ("S009", "広島店", "中国・九州", date(2023, 1, 1)),
    ("S010", "福岡店", "中国・九州", date(2026, 3, 15)),
]
CATEGORIES = {"食品": 180_000, "日用品": 90_000, "文具": 40_000}
SCALE = {"S003": 1.6, "S007": 1.5, "S005": 1.2, "S004": 1.3}

rows = []
day = date(2026, 4, 1)
while day <= date(2026, 9, 30):
    for code, _, _, opened in STORES:
        if day < opened:
            continue
        for category, base in CATEGORIES.items():
            amount = int(base * SCALE.get(code, 1.0) * random.uniform(0.7, 1.3))
            rows.append((day.isoformat(), code, category, "通常", amount))
            if random.random() < 0.05:
                rows.append((day.isoformat(), code, category, "返品", -int(amount * random.uniform(0.05, 0.3))))
            if random.random() < 0.03:
                rows.append((day.isoformat(), code, category, "社内販売", int(amount * random.uniform(0.2, 0.8))))
    day += timedelta(days=1)

header = ("日付", "店舗コード", "商品カテゴリ", "区分", "金額")

# CSV（Excelで開いても文字化けしないようにBOM付きのUTF-8）
with open(OUT / "sales_2026h1.csv", "w", encoding="utf-8-sig", newline="") as f:
    f.write(",".join(header) + "\n")
    for r in rows:
        f.write(",".join(map(str, r)) + "\n")

# 比較用に、Excelの「CSV（コンマ区切り）」と同じShift_JISでも保存する
with open(OUT / "sales_2026h1_sjis.csv", "w", encoding="cp932", newline="") as f:
    f.write(",".join(header) + "\n")
    for r in rows:
        f.write(",".join(map(str, r)) + "\n")

# 同じ明細をMarkdownの表にした文書
with open(OUT / "sales_2026h1.md", "w", encoding="utf-8") as f:
    f.write("# 売上明細（2026年4月〜9月）\n\n")
    f.write("店舗ごと・日ごと・商品カテゴリごとの売上明細です。金額の単位は円です。\n\n")
    f.write("| " + " | ".join(header) + " |\n")
    f.write("|" + "---|" * len(header) + "\n")
    for r in rows:
        f.write("| " + " | ".join(map(str, r)) + " |\n")

# 店舗マスタ（日本語のシート名）
wb = Workbook()
ws = wb.active
ws.title = "店舗一覧"
ws.append(["店舗コード", "店舗名", "地域", "開店日"])
for code, name, region, opened in STORES:
    ws.append([code, name, region, opened])
    ws.cell(row=ws.max_row, column=4).number_format = "yyyy/mm/dd"
log = wb.create_sheet("更新履歴")
log.append(["更新日", "内容"])
log.append([date(2026, 3, 15), "福岡店を追加"])
log.append([date(2025, 12, 1), "横浜店を追加"])
log.append([date(2025, 9, 15), "京都店を追加"])
wb.save(OUT / "stores.xlsx")

(OUT / "sales_rules.md").write_text(
    """# 売上集計ルール

店舗の月次売上を報告するときの集計ルールです。

## 純売上

月次報告の売上は純売上で出します。純売上は売上明細の金額のうち、区分が「通常」と「返品」の行を合計した値です。
返品は金額がマイナスで記録されているので、そのまま足せば差し引かれます。
区分が「社内販売」の行は従業員向けの販売なので、純売上には含めません。

## 既存店

既存店との比較では、集計する月の初日の時点で開店から12か月以上たっている店舗を既存店とします。
開店日は店舗マスタで確認してください。開店から12か月に満たない店舗は新店として別に報告します。

## 締め日

月次の締めは月末日です。翌月5営業日目までに各店舗の店長が数字を確定します。
""",
    encoding="utf-8",
)

print(f"rows={len(rows)}")
for p in sorted(OUT.iterdir()):
    print(p.name, p.stat().st_size)
