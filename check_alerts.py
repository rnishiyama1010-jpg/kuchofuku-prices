"""prices.json の最安値が alerts.json の金額を下回ったら、GitHub の Issue を立てて知らせる。

- 下回ったとき：その型番の Issue（ラベル price-alert）が開いていなければ新しく立てる。
- 金額が戻ったとき：開いている Issue に「戻りました」と書いて閉じる（次に下がったらまた立つ）。
GitHub Actions から gh コマンドで実行する（GH_TOKEN が必要）。
"""
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = {"rakuten": "楽天市場", "yahoo": "Yahoo!ショッピング"}
LABEL = "price-alert"


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def open_issue_number(item_id):
    out = gh("issue", "list", "--label", LABEL, "--state", "open",
             "--json", "number,title", "--limit", "100")
    for it in json.loads(out):
        if it["title"].startswith(f"【値下がり】{item_id} "):
            return it["number"]
    return None


def main():
    with open(os.path.join(HERE, "alerts.json"), encoding="utf-8") as f:
        alerts = json.load(f)["items"]
    with open(os.path.join(HERE, "prices.json"), encoding="utf-8") as f:
        prices = json.load(f)
    updated = prices.get("updated", "")

    try:
        gh("label", "create", LABEL, "--color", "D93F0B",
           "--description", "最安値のお知らせ")
    except subprocess.CalledProcessError:
        pass  # すでにある

    for item_id, limit in alerts.items():
        item = prices["items"].get(item_id) or {}
        low = item.get("lowest") or {}
        price = low.get("price")
        if not price:
            print(f"{item_id}: 価格なし（スキップ）")
            continue
        number = open_issue_number(item_id)
        if price < limit:
            if number:
                print(f"{item_id}: {price}円（{limit}円未満、お知らせ済み #{number}）")
                continue
            shop = item.get(low.get("site"), {})
            body = (
                f"@rnishiyama1010-jpg {item_id} の最安値が {limit:,}円 を切りました。\n\n"
                f"- 最安値：**{price:,}円**（{SITE.get(low.get('site'), low.get('site'))}・{shop.get('shop', '')}）\n"
                f"- 商品：{shop.get('name', '')}\n"
                f"- 送料：{'無料' if shop.get('freeShipping') else '別の場合あり'}\n"
                f"- リンク：{shop.get('url', '')}\n"
                f"- 取得：{updated}\n\n"
                "YouTubeのコミュニティ投稿でお知らせしてください。\n"
                "比較サイト：https://www.stockmedia.biz/battery\n\n"
                f"値段が {limit:,}円 以上に戻ると、このIssueは自動で閉じます。"
            )
            out = gh("issue", "create", "--title", f"【値下がり】{item_id} が {price:,}円 になりました",
                     "--label", LABEL, "--body", body)
            print(f"{item_id}: {price}円 → Issue を作成 {out.strip()}")
        else:
            if number:
                gh("issue", "close", str(number), "--comment",
                   f"最安値が {price:,}円 に戻ったので閉じます（{updated}）。")
                print(f"{item_id}: {price}円 → #{number} を閉じた")
            else:
                print(f"{item_id}: {price}円（{limit}円以上）")


if __name__ == "__main__":
    main()
