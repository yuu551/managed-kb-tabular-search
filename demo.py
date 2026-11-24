import json
import sys
import time
from pathlib import Path

import boto3
from botocore.config import Config

REGION = "us-east-1"
STATE = Path("state.json")
DATA = Path("data")
PREFIX = "tables/"

session = boto3.Session(region_name=REGION)
s3 = session.client("s3")
iam = session.client("iam")
agent = session.client("bedrock-agent")
# コードを動かす質問は1分以上かかることがあるので読み取りのタイムアウトを長くする
runtime = session.client("bedrock-agent-runtime", config=Config(read_timeout=600))

# 比較のために、売上明細をCSVで読む組とMarkdownの表で読む組を用意する
FILE_SETS = {
    "csv": ["sales_2026h1.csv", "stores.xlsx", "sales_rules.md"],
    "md": ["sales_2026h1.md", "stores.xlsx", "sales_rules.md"],
}
QUESTIONS = {
    "A": "2026年9月の売上明細の金額を、区分を問わず店舗ごとに合計してください。合計が多い順に上位3店舗の店舗コードと金額を教えてください。",
    "B": "売上集計ルールに沿って、2026年9月の既存店の純売上を地域別に教えてください。",
    "C": "店舗コードS006の開店日はいつですか？",
    "D": "返品の行は純売上でどのように扱いますか？",
}


def state():
    return json.loads(STATE.read_text())


def save_state(s):
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2))


def wait(label, fetch, done, failed=()):
    while True:
        status = fetch()
        print(f"  {label}: {status}", flush=True)
        if status in done:
            return
        if status in failed:
            raise RuntimeError(f"{label} {status}")
        time.sleep(10)


def setup():
    account = session.client("sts").get_caller_identity()["Account"]
    name = f"tabular-demo-{int(time.time())}"
    s = {"name": name, "bucket": f"{name}-{account}"}
    save_state(s)

    s3.create_bucket(Bucket=s["bucket"])
    for path in sorted(DATA.iterdir()):
        s3.upload_file(str(path), s["bucket"], PREFIX + path.name)

    trust = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "bedrock.amazonaws.com"},
            "Action": "sts:AssumeRole",
            "Condition": {
                "StringEquals": {"aws:SourceAccount": account},
                "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock:{REGION}:{account}:knowledge-base/*"},
            },
        }],
    }
    read_bucket = {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": "s3:ListBucket", "Resource": f"arn:aws:s3:::{s['bucket']}"},
            {"Effect": "Allow", "Action": "s3:GetObject", "Resource": f"arn:aws:s3:::{s['bucket']}/*"},
        ],
    }
    s["roleArn"] = iam.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps(trust))["Role"]["Arn"]
    iam.put_role_policy(RoleName=name, PolicyName="read-bucket", PolicyDocument=json.dumps(read_bucket))
    save_state(s)
    time.sleep(15)  # ロールが使えるようになるまで待つ

    kb = agent.create_knowledge_base(
        name=name,
        roleArn=s["roleArn"],
        knowledgeBaseConfiguration={
            "type": "MANAGED",
            "managedKnowledgeBaseConfiguration": {"embeddingModelType": "MANAGED"},
        },
    )["knowledgeBase"]
    s["kbId"] = kb["knowledgeBaseId"]
    save_state(s)
    wait("knowledge base",
         lambda: agent.get_knowledge_base(knowledgeBaseId=s["kbId"])["knowledgeBase"]["status"],
         {"ACTIVE"}, {"FAILED"})

    ds = agent.create_data_source(
        knowledgeBaseId=s["kbId"],
        name="tables",
        dataSourceConfiguration={
            "type": "MANAGED_KNOWLEDGE_BASE_CONNECTOR",
            "managedKnowledgeBaseConnectorConfiguration": {
                "connectorParameters": {
                    "type": "S3",
                    "version": "1",
                    "connectionConfiguration": {"bucketName": s["bucket"], "bucketOwnerAccountId": account},
                    "filterConfiguration": {"maxFileSizeInMegaBytes": "200", "inclusionPrefixes": [PREFIX]},
                    "aclEnabled": False,
                }
            },
        },
        vectorIngestionConfiguration={"parsingConfiguration": {"parsingStrategy": "SMART_PARSING"}},
    )["dataSource"]
    s["dsId"] = ds["dataSourceId"]
    save_state(s)
    print(json.dumps(s, indent=2))


def sync():
    s = state()
    ids = {"knowledgeBaseId": s["kbId"], "dataSourceId": s["dsId"]}
    job_id = agent.start_ingestion_job(**ids)["ingestionJob"]["ingestionJobId"]
    started = time.time()
    while True:
        job = agent.get_ingestion_job(**ids, ingestionJobId=job_id)["ingestionJob"]
        print(f"  ingestion: {job['status']} ({time.time() - started:.0f}s)", flush=True)
        if job["status"] in ("COMPLETE", "FAILED", "STOPPED"):
            break
        time.sleep(15)
    print(json.dumps({k: job.get(k) for k in ("status", "statistics", "failureReasons")},
                     ensure_ascii=False, indent=2, default=str))


def docs():
    """ファイルごとの取り込みの状態を見る"""
    s = state()
    res = agent.list_knowledge_base_documents(knowledgeBaseId=s["kbId"], dataSourceId=s["dsId"])
    for d in res["documentDetails"]:
        print(d["identifier"]["s3"]["uri"].split("/")[-1], d["status"], d.get("statusReason", ""))


def file_types():
    """ファイルごとに付いた _file_type を Retrieve の結果から見る"""
    s = state()
    seen = {}
    for query in ["売上明細 金額 区分", "店舗マスタ 開店日", "売上集計ルール 純売上"]:
        res = runtime.retrieve(
            knowledgeBaseId=s["kbId"],
            retrievalQuery={"text": query},
            retrievalConfiguration={"managedSearchConfiguration": {"numberOfResults": 20}},
        )
        for r in res["retrievalResults"]:
            m = r.get("metadata", {})
            seen[m.get("_document_title")] = m.get("_file_type")
    for title, file_type in sorted(seen.items()):
        print(f"{title:<20} {file_type}")


def retrieve(qid):
    s = state()
    res = runtime.retrieve(
        knowledgeBaseId=s["kbId"],
        retrievalQuery={"text": QUESTIONS[qid]},
        retrievalConfiguration={"managedSearchConfiguration": {
            "numberOfResults": 10,
            "filter": {"in": {"key": "_document_title", "value": FILE_SETS["csv"]}},
        }},
    )
    for i, r in enumerate(res["retrievalResults"], 1):
        m = r.get("metadata", {})
        text = " ".join(r["content"].get("text", "").split())
        print(f"{i:>2}. {m.get('_document_title')} ({m.get('_file_type')}) {text[:100]}")


def ask(qid, file_set, tag=""):
    s = state()
    out = Path("evidence", f"{qid}-{file_set}{tag}.jsonl")
    out.parent.mkdir(exist_ok=True)
    started = time.time()
    response = runtime.agentic_retrieve_stream(
        messages=[{"role": "user", "content": {"text": QUESTIONS[qid]}}],
        retrievers=[{"configuration": {"knowledgeBase": {
            "knowledgeBaseId": s["kbId"],
            # 読むファイルをメタデータのフィルターで絞る
            "retrievalOverrides": {"filter": {"in": {"key": "_document_title", "value": FILE_SETS[file_set]}}},
        }}}],
        agenticRetrieveConfiguration={"foundationModelType": "MANAGED", "rerankingModelType": "MANAGED"},
    )
    answer, code_files, steps = [], [], []
    with out.open("w") as f:
        for event in response["stream"]:
            t = time.time() - started
            f.write(json.dumps({"t": round(t, 2), "event": event}, ensure_ascii=False, default=str) + "\n")
            if "traceEvent" in event:
                a = event["traceEvent"]["attributes"]
                step = (a.get("step"), a.get("status"))
                if not steps or steps[-1] != step:
                    steps.append(step)
                    print(f"[{t:5.1f}s] {a.get('step')} {a.get('status')} {a.get('message', '')}", flush=True)
                for action in a.get("actions", []):
                    for doc in (action.get("codeExecution") or {}).get("documents", []):
                        code_files.append(doc["documentId"])
                        print(f"         コードが読むファイル: {doc['documentId']}")
            elif "responseEvent" in event:
                answer.append(event["responseEvent"]["text"])
    print(f"\n--- 回答（{time.time() - started:.1f}秒） ---\n" + "".join(answer))


def cleanup():
    s = state()
    if "dsId" in s:
        agent.delete_data_source(knowledgeBaseId=s["kbId"], dataSourceId=s["dsId"])
    if "kbId" in s:
        agent.delete_knowledge_base(knowledgeBaseId=s["kbId"])
    bucket = session.resource("s3").Bucket(s["bucket"])
    bucket.objects.all().delete()
    bucket.delete()
    iam.delete_role_policy(RoleName=s["name"], PolicyName="read-bucket")
    iam.delete_role(RoleName=s["name"])
    STATE.unlink()
    print("deleted")


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    {"setup": setup, "sync": sync, "docs": docs, "file-types": file_types, "retrieve": retrieve,
     "ask": ask, "cleanup": cleanup}[command](*args)
