# kuchofuku-prices

Stock合同会社（stockmedia.biz）の空調服バッテリー比較ページで使う最安値データです。

- `products.json`：対象製品と検索条件（型番・除外語・参考価格）
- `fetch_prices.py`：楽天市場とYahoo!ショッピングのAPIで最安値を取得し、`prices.json` に書き出す
- `.github/workflows/update-prices.yml`：毎朝 5:47（日本時間）に自動実行
- `prices.json`：公開データ（GitHub Pages で配信）

APIキーは GitHub の Secrets に保存し、このリポジトリには含めません。
製品を追加するときは `products.json` に1行足します。

アフィリエイト：楽天市場・Yahoo!ショッピングはもしもアフィリエイト（どこでもリンク）、Amazonはアソシエイト（stockmedia-22）。楽天・Yahoo!の商品URLは `prices.json` に素のまま保存し、ページ側でもしものリンクに包みます。
