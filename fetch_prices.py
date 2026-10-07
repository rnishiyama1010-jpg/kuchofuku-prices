"""楽天市場・Yahoo!ショッピングの最安値を取得して prices.json に書き出す。

キーは環境変数（GitHub Secrets）から読む。リポジトリには書かない。
  RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY / YAHOO_CLIENT_ID
任意（アフィリエイト登録後）:
  RAKUTEN_AFFILIATE_ID / YAHOO_VC_AFFILIATE_ID
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
SITE = "https://stockmedia.biz/"
UA = "kuchofuku-prices/1.0 (+https://stockmedia.biz/)"
RAKUTEN_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
YAHOO_URL = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
# 参考価格からこの範囲を外れる結果は、付属品やウェア込みセットとみなして除外する
FLOOR, CEIL = 0.6, 1.6
COMMON_NG = ["中古", "未使用品", "USED", "箱無し", "フルセット", "ブルゾン", "ジャケット", "ベスト付", "訳あり", "ジャンク", "互換", "保護フィルム", "交換用ケーブルのみ"]
# 中古品を主に扱う店は除外する
NG_SHOPS = ["セカンドストリート", "2nd STREET", "ボーダレス", "BORDERLESS", "ブックオフ", "ハードオフ", "トレジャーファクトリー"]


def ng_shop(name):
    n = norm(name)
    return any(norm(s) in n for s in NG_SHOPS)


def norm(s):
    s = unicodedata.normalize("NFKC", s or "").upper()
    return re.sub(r"[\s\-_‐－]", "", s)


def matches(name, p):
    n = norm(name)
    if not all(norm(t) in n for t in p["must"]):
        return False
    if p["any"] and not any(norm(t) in n for t in p["any"]):
        return False
    for t in p["ng"] + COMMON_NG:
        nt = norm(t)
        # 型番のNGは「型番そのもの」が別型番の一部として出るのを防ぐ
        if nt and nt in n and not any(nt == norm(m) for m in p["must"]):
            return False
    return True


RAW = {}


def get_json(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def rakuten(p):
    params = {
        "applicationId": os.environ["RAKUTEN_APP_ID"],
        "accessKey": os.environ["RAKUTEN_ACCESS_KEY"],
        "keyword": p["keyword"],
        "sort": "+itemPrice",
        "hits": 30,
        "availability": 1,
        "formatVersion": 2,
        "usedExcludeFlag": 1,
        # 付属品（ケーブル・アダプター等）で上位が埋まらないよう、価格帯をAPI側で絞る
        "minPrice": int(p["ref"] * FLOOR),
        "maxPrice": int(p["ref"] * CEIL),
        "NGKeyword": "変換 ケース ポーチ",
    }
    if os.environ.get("RAKUTEN_AFFILIATE_ID"):
        params["affiliateId"] = os.environ["RAKUTEN_AFFILIATE_ID"]
    url = RAKUTEN_URL + "?" + urllib.parse.urlencode(params)
    data = get_json(url, {"Referer": SITE, "Origin": SITE.rstrip("/")})
    items = data.get("Items") or data.get("items") or []
    RAW[(p["id"], "rakuten")] = [((i.get("Item", i)).get("itemName", "")[:80], (i.get("Item", i)).get("itemPrice")) for i in items[:12]]
    best = None
    for it in items:
        it = it.get("Item", it)
        price = int(it.get("itemPrice") or 0)
        if not price or not matches(it.get("itemName"), p) or ng_shop(it.get("shopName")):
            continue
        if not (p["ref"] * FLOOR <= price <= p["ref"] * CEIL):
            continue
        if best is None or price < best["price"]:
            best = {
                "price": price,
                "url": it.get("affiliateUrl") or it.get("itemUrl"),
                "shop": it.get("shopName"),
                "freeShipping": it.get("postageFlag") == 0,
                "name": it.get("itemName"),
            }
    return best


def yahoo(p):
    params = {
        "appid": os.environ["YAHOO_CLIENT_ID"],
        "query": p["keyword"],
        "sort": "+price",
        "results": 50,
        "in_stock": "true",
        "condition": "new",
        "price_from": int(p["ref"] * FLOOR),
        "price_to": int(p["ref"] * CEIL),
    }
    if os.environ.get("YAHOO_VC_AFFILIATE_ID"):
        params["affiliate_type"] = "vc"
        params["affiliate_id"] = os.environ["YAHOO_VC_AFFILIATE_ID"]
    data = get_json(YAHOO_URL + "?" + urllib.parse.urlencode(params))
    RAW[(p["id"], "yahoo")] = [(h.get("name", "")[:80], h.get("price")) for h in data.get("hits", [])[:12]]
    best = None
    for it in data.get("hits", []):
        price = int(it.get("price") or 0)
        if not price or not matches(it.get("name"), p) or ng_shop((it.get("seller") or {}).get("name")):
            continue
        if not (p["ref"] * FLOOR <= price <= p["ref"] * CEIL):
            continue
        if best is None or price < best["price"]:
            ship = it.get("shipping") or {}
            best = {
                "price": price,
                "url": it.get("url"),
                "shop": (it.get("seller") or {}).get("name"),
                "freeShipping": "無料" in str(ship.get("name", "")),
                "name": it.get("name"),
            }
    return best


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    products = json.load(open(os.path.join(here, "products.json"), encoding="utf-8"))
    out_path = os.path.join(here, "prices.json")
    try:
        prev = json.load(open(out_path, encoding="utf-8")).get("items", {})
    except Exception:
        prev = {}

    items, errors = {}, []
    for p in products:
        row = {}
        for site, fn in (("rakuten", rakuten), ("yahoo", yahoo)):
            try:
                row[site] = fn(p)
            except Exception as e:  # 1サイトの失敗で全体を止めない
                errors.append(f"{p['id']} {site}: {e}")
                row[site] = (prev.get(p["id"]) or {}).get(site)
            time.sleep(1.1)  # 各APIの1秒1回の制限を守る
        cands = [(v["price"], k) for k, v in row.items() if v]
        row["lowest"] = {"site": min(cands)[1], "price": min(cands)[0]} if cands else None
        items[p["id"]] = row

    out = {
        "updated": datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "note": "楽天市場・Yahoo!ショッピングの税込価格（送料別の場合あり）。Amazonは掲載規約により未掲載。",
        "items": items,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    # 最安値が取れなかった製品の検索結果を残し、条件調整に使う
    diag = {f"{k[0]} {k[1]}": v for k, v in RAW.items() if not items.get(k[0], {}).get(k[1])}
    with open(os.path.join(here, "diagnostics.json"), "w", encoding="utf-8") as f:
        json.dump(diag, f, ensure_ascii=False, indent=1)
    found = sum(1 for v in items.values() if v["lowest"])
    print(f"updated {found}/{len(items)} items")
    for e in errors:
        print("ERROR", e, file=sys.stderr)
    # 全件失敗（キー誤りなど）のときはジョブを失敗させて気づけるようにする
    if found == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
