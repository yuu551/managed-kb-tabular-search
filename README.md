# Amazon Bedrock Managed Knowledge Base 表検索（tabular search）の検証

Amazon Bedrock Managed Knowledge Base の表検索を、日本語の列名・シート名の売上明細（CSV）と店舗マスタ（Excel）で試すサンプルです。
エージェント検索（AgenticRetrieveStream）の回答を、pandas で出した正解と突き合わせます。

記事: https://dev.classmethod.jp/articles/bedrock-managed-kb-tabular-search/

## 前提

- Python 3.15 と [uv](https://docs.astral.sh/uv/)
- boto3 1.43.123 以降（動作を確認したのは 1.44.9）
- AWS の認証が済んでいること（リージョンは us-east-1）
- IAM ロール・S3 バケット・ナレッジベースを作成できる権限

## セットアップ

```bash
uv sync
```

## 実行の流れ

```bash
# 架空のデータを data/ に作り、pandas で正解を出す
uv run make_data.py
uv run answers.py

# S3 バケット・IAM ロール・ナレッジベース・データソースを作って取り込む
uv run demo.py setup
uv run demo.py sync
uv run demo.py docs        # ファイルごとの取り込みの状態
uv run demo.py file-types  # ファイルごとの _file_type

# 質問する（A〜D は demo.py の QUESTIONS、csv / md は読めるファイルの組）
uv run demo.py retrieve A
uv run demo.py ask A csv
uv run demo.py ask A md
uv run demo.py ask B csv
uv run demo.py ask C csv
uv run demo.py ask D csv

# 作ったものをすべて削除する
uv run demo.py cleanup
```

作成したリソースの ID は `state.json`、質問ごとのストリームのイベントは `evidence/` に保存されます。

## ファイル

| ファイル | 内容 |
| --- | --- |
| make_data.py | 架空の10店舗の売上明細（CSV・Shift_JIS の CSV・Markdown の表）、店舗マスタ（Excel）、売上集計ルール（Markdown）を作る |
| answers.py | 質問 A と B の正解を pandas で出す |
| demo.py | ナレッジベースの作成・取り込み・質問・後片付けをサブコマンドで実行する |

## 質問

| ID | 質問 |
| --- | --- |
| A | 2026年9月の売上明細の金額を、区分を問わず店舗ごとに合計した上位3店舗 |
| B | 売上集計ルールに沿った、2026年9月の既存店の純売上（地域別） |
| C | 店舗コード S006 の開店日 |
| D | 返品の行は純売上でどのように扱うか |

## 注意

- データはすべて架空のものです
- ナレッジベースとエージェント検索の利用料金がかかります。試し終わったら `uv run demo.py cleanup` で削除してください
