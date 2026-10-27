# RECORD v0.88：検索時の公式発売情報取得を検証

2026-10-27。今回はアーティスト・作品を追加せず、公開目次はv0.87の20組・292作品を維持する。アーティスト追加案のPR #35は別件で未マージ。この検証はそれを前提にせず、mainのv0.87を基にする。

## 現時点の結論

通常のHTTPS取得と既存の共通アダプターで、未登録のWillie Nelsonの発売作品を抽出し、作品名・発売年・発売元・根拠URLを出力する試作品は動作した。ただし、GitHub Pagesのブラウザだけで検索時に公式ディスコグラフィーを探索する本番機能への移行は未達成。

取得したHTMLのCORSヘッダー観測では、本人の一覧、Warner、Blue Noteの一覧はいずれもPages Originへの許可がない。一部の本人商品ページだけ `Access-Control-Allow-Origin: *` があっても、一覧探索の成立を意味しない。HTTPクライアントで200が返ること、ブラウザが本文を読めること、正式発売の証拠が揃うことは別々に評価する。ブラウザ実測の結果はPRのCIに記録する。

## 自動取得・確認した作品（公開目次には未登録）

| 作品 | 発売年 | 発売元・掲載元 | 根拠URL |
| --- | --- | --- | --- |
| ザ・コンプリート・アトランティック・セッションズ | 2006 | Warner Music Japan | https://wmg.jp/WillieNelson/discography/3355 |
| American Classic | 2009 | Blue Note Records | https://www.bluenote.com/artist/willie-nelson/ |

WarnerはALBUM区分、名義、2006-08-23の発売済み日付を既存 `warner-albums-v1` で照合。2006はこの掲載盤の年で、収録録音や初回作品の年ではない。Blue Noteは既存 `bluenote-artist-v1` で本人単独名義と2009年の発売作品掲載を照合。共演名義など、既存ルールでは照合できない2候補を保留した。MusicBrainzや配信確認による二重認定は使用しない。

本人ディスコグラフィーの先頭ページから24個の商品リンクを重複なく抽出できた。負荷を抑えた試験として先頭3商品の詳細まで取得したが、ShopifyのProduct情報・vendor・記事公開日時だけでは音楽アルバムの名義・発売日・発売元を安全に照合できないため、確認済み作品一覧には出していない。公式発売がないという判断ではなく、今回の自動照合ルールでは情報不足。

この3ページという取得予算は技術検証の負荷制限で、アーティストの登録作品数上限ではない。全ディスコグラフィーを調べ終えたという意味でもない。

- [実行時の確認結果・公式URL・SHA-256](experiments/willie-nelson-http-2026-10-27.json)
- [先行するHTTP/CORSヘッダー観測](experiments/willie-nelson-initial-http-2026-10-27.json)

## アーティストの事前登録なしの探索も検証

既存の `server/search.py` の公式ディレクトリー探索を、アーティスト名義の登録をすべて外した設定で実行した。Blue Note / Warnerの公式アーティスト一覧からWillie Nelsonの入口を自動発見でき、Blue NoteからAmerican Classicを1作品確認できた。Sonyの一覧は404、Warnerで発見した標準ディスコグラフィーは書式照合エラーとなり、結果はpartial。これは全作品確認済みという意味ではない。

[実際の探索結果](experiments/willie-nelson-directory-2026-10-27.json)を保存した。既存任意APIの `year` はnullだったが、確認証拠 `listedReleaseYear` に2009がある。今回のCLIは証拠にある年だけを表示年に使う。任意APIや公開画面のコード自体は変更しない。メモリー内の一時キャッシュだけで試験し、DBファイルや常駐サーバーは作成しない。

```sh
python scripts/probe_official_search.py --directory-search --artist 'Willie Nelson' --output-dir /tmp/record-probe/discovery
```

この汎用探索モードは検索ごとに本人の公式ドメインを推測するのではなく、既存の許可済みレコード会社公式一覧から名前の一致を探す。本人サイトの全自動発見、翻字や別名の推測、任意の公式サイト書式への対応は未実現。最初の公式入口を指定したモードの2作品と、ディレクトリー探索だけで確認した1作品を混同しない。

## 試作品の構成と再実行

`scripts/probe_official_search.py` は本番検索から切り離した読み取り専用のCLI。既存のWarner・Blue Note・MusicAlbum/MusicRelease照合処理とURL検証を再利用する。公式一覧と商品ページを実行時に取得し、確認済みの作品だけをJSONとHTMLへ出力する。

```sh
python scripts/probe_official_search.py --artist 'Willie Nelson' --output-dir /tmp/record-probe
```

生成するHTMLは実行時のスナップショットで、開くたびに調査するページではない。Willie Nelson用に確認済みの公式入口を指定しており、このCLI自体は任意のアーティストの公式サイトをインターネット全体から発見する検索エンジンではない。未対応の入力はドメインを推測せず、未対応とする。公開目次への追記、DB、サーバー起動は行わない。

`scripts/probe_official_browser.py` はChromium内の通常の `fetch(mode: cors, credentials: omit)` を使用する。Pagesと同じOriginの検証用文書だけをローカル応答し、公式URLへのGETは実通信。CORSを無効にする起動引数、認証、ログイン情報、公開プロキシは使わない。実際の公開トップページを変更・再公開する試験ではない。取得エラーだけでCORS・通信断・アクセス拒否を断定せず、HTTP観測とブラウザのCORSエラーを突き合わせる。

`.github/workflows/official-source-probe.yml` で同じ読み取り専用試験を実行できる。検証コード変更のPRと手動起動だけで動作し、定期実行・自動コミット・自動公開は設定していない。新規workflowの手動起動はdefault branchへのマージ後に利用可能。権限はcontents: readのみ。公式入口を指定したモードのHTTPは1実行最大7ページ、同一ホストに1秒以上の間隔、12秒タイムアウト、応答2MBまで。401/403/429は同一ホストの後続取得も中止し、リトライ・別IP・別ドメインへの迂回をしない。汎用探索モードは既存の上限（公式ディレクトリー3件、発見元ごと最大2入口、全体最大8入口）とホスト単位の取得間隔・拒否時の停止を再利用する。ブラウザ測定は固定4URLを各2回だけ取得する。資料本文・画像は保存せず、診断結果のみ小さなartifactにして1日で削除する。

## 方式の違い・費用・制約

| 方式 | 検索時に新しい公式情報を取得 | 構成・費用 | 制約 |
| --- | --- | --- | --- |
| Pagesブラウザから直接 | 相手がCORSを許可すれば可能 | 現在のPagesのみ、追加費用なし | 今回の主要一覧では許可なし。任意の公式サイト発見、書式差、負荷集約も課題 |
| Pages + Actionsの手動・定期更新 | いいえ。実行時点の資料を静的JSONへ更新 | 公開リポジトリの標準GitHub-hosted runnerは無料。新サービス登録不要 | 更新まで待つ。定期実行は遅延・未実行があり得る。60日活動なしで停止する場合がある |
| Pages + 認証付きのActions要求キュー | 擬似的なオンデマンド、即時応答ではない | 既存GitHub内で検討可能 | 起動待ち＋取得＋公開待ち。一般利用者から安全に起動する認証・要求受付が必要。トークンをPagesに埋め込めない |
| Pages + 外部の検索処理（例: Workers） | 可能性あり、今回未実装 | Freeは10万request/日・CPU 10ms/request。有料標準は月$5〜 | 公式サイトへの通常アクセス可否と利用条件、HTML処理CPU、レート制限、キャッシュ、悪用防止の設計が必要。外部登録は未実施 |
| Pages + 既存Python検索コードを外部サーバーで実行 | 構成上は可能、今回未導入 | ホスティング・保存先の料金と無料枠次第 | 無料枠の休止・遅延・永続保存、運用、認証・負荷制御が必要。サービス選定・契約は別途承認 |

GitHub Pagesは静的ホスティングで、検索時にPythonを実行できない。ブラウザの `no-cors` は本文を読めないopaque応答になるため解決策にならない。Actionsから通常の公式HTTPSを取得できても、Pages上の検索がリアルタイムになったと説明してはいけない。外部処理でも401/403/429を回避することは認めない。

料金は2026-10-27に公式資料を確認。公開repoの標準runnerを前提とし、大型runner・非公開repo・ストレージ超過は無料と一括りにしない。artifactは小さく1日保持。課金プランへの変更・外部サービスの登録は今回行っていない。

公式技術資料：

- [GitHub Pagesの構成](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)
- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [Actions起動条件・scheduleの制約](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [MDN CORSのエラーとopaque応答](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors)
- [Cloudflare Workers料金](https://developers.cloudflare.com/workers/platform/pricing/)

## 次の手順と未実現事項

無料・GitHub内のみを維持する場合、次に進めやすいのは「公式取得と厳格な照合 → 確認結果を保存 → Pages用JSONを更新」というActions経由の方式。ただし、これは検索時のリアルタイム調査とは区別する。今回のPRはその検証用入口までとし、本番への自動登録・定期公開は有効化しない。

任意の未登録アーティストをその場で調べる本来の目標には、公式入口の自動発見、各書式への対応、本人・名義・発売元・発売済みの照合、共有キャッシュとアクセス予算が必要。既存 `server/search.py` の公式ディレクトリー探索・照合・期限付き保存は将来利用できるが、Pagesだけでは動かない。本番の外部構成を導入する場合にのみ改めて承認を得る。

公開 `index.html`、292作品、公式URL、直接リンク、検索、保存、バックアップ・復元、実行モードと公式ソース設定は変更していない。既存CIに加え、誤名義・未来日・不足する発売証拠・403・URL境界・取得予算・HTMLエスケープ・公開ファイル完全一致をテストする。iPhone実機Safariでの検証は未実施。
