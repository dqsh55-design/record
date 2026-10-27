# 公式ディスコグラフィーの継続追加

公開目次は引き続き `data/official-catalog.json` のみ。収集結果は公開に使用しない。

## 定期取得

`Collect official discography candidates` は毎週月曜12:25 JSTと手動実行に対応。
`data/official-sources.json` の有効な情報源（Blue Noteのノラ、Warner Music Japanのマイルス）を取得し、Actionsの `official-discography-candidates` 成果物に候補JSONを90日保存する。書き込み権限なし、目次への自動認定なし。取得日時、ページハッシュ、件数、HTTP失敗、抽出0件（構造変更の疑い）を記録する。失敗時も成果物を保存しジョブを失敗として通知する。各実行は独立したスナップショット。前回成果物を自動ダウンロードしない。

Blue Noteはrelease-entry内の作品見出しを抽出し、バンドとの複合名義を除外する。外部販売リンクを根拠URLにしない。マイルスはWarner公式の本人ディスコグラフィー内、ALBUM表記を持つカードの見出しと商品URLだけを候補化する。Sony運営の米国公式一覧とSony日本公式は通常取得で403のため無効化し、理由をレポートに残す。無効な情報源には通信しない。IP・User-Agentの偽装、プロキシ、認証回避、非公開APIの探索は行わない。候補だけでは作品種別やレーベルを保証しない。ページ送りは未対応なので全件網羅とはしない。

## レビューと追加

1. `python scripts/official_discography.py collect --report reports/official-candidates.json`
2. 各公式資料で作品名・本人名義・アルバム種別・発売元を確認。作品単位の確認であり、個別再発盤やYouTube配信の認定には使わない。
3. レビューJSONを作成（次の例のIDは候補JSONからコピー）。資料が不十分ならrejectまたは未登録のままにする。発売年不明ならnull。

```json
[
  {
    "candidateId": "候補のid",
    "candidateTitle": "候補のtitleをそのままコピー",
    "sourceSha256": "同じレポートの該当sourceのsha256",
    "decision": "approve",
    "title": "公式資料で確認した作品名",
    "year": null,
    "label": "公式資料で確認した発売元",
    "checkedAt": "2026-10-27",
    "reviewer": "確認者名",
    "note": "確認した資料内容と判断理由"
  }
]
```

4. `python scripts/official_discography.py publish --report reports/official-candidates.json --reviews reviews.json`
5. 差分確認・テスト後PRにする。公開はPRのマージ後。利用者に作品ごとの確認を依頼する想定ではなく、開発・運用側の確認作業。

承認のない候補は追加されない。重複作品はスキップ、既存ID・確認日・根拠は維持。不正レビューが一件でもあれば全体を中止し、ファイルを置換しない。取得失敗・無効化した情報源の承認も拒否。レビューは取得ページのハッシュと候補の元タイトルに結び付け、別の取得結果との取り違えを拒否する。これはデータの真偽を暗号的に保証する仕組みではなく、運用時の取り違えを防ぐチェック。ページが更新された場合は再確認し、新しいハッシュでレビューを作る。既存作品の削除や出典の自動更新はしない。アーティスト追加時は公開目次に名義・別名・空albumsと、公式sources設定をPRで追加する。新ホストはブラウザ側officialSourceHostsの追加レビューも必要。

## 検証（2026-10-27 JST）

公式目次はノラ12作品を維持。Warner公式の商品ページで本人名義・英題・ALBUM区分を確認したDoo-BopとTUTUの2作品を追加し、マイルスは6→8作品。両作品とも今回の資料の再発日を初回発売年に転用せずyear=null。Warner Music Japanを発売元として登録。YouTube Music配信・再生は未確認。

14件の収集・登録テスト（ノラ12候補を空目次へCLIで登録→再実行→既存目次の全項目維持、不正バッチ時のファイル維持、実ページ由来の縮小構造での再抽出、無効情報源への通信禁止など）、既存Python照合32件、Node全7スイートを検証。画面テストはノラ12→マイルス8の切替、Doo-Bop/TUTU表示と根拠リンクを確認する。

`tests/fixtures/official-observations.json` は通常HTTPSで取得した候補と元ページのハッシュ。HTMLフィクスチャは実ページで観察した見出し・カードの構造を縮小再構成したもので、全文の保存ではない。全ページハッシュは縮小HTMLのハッシュとは異なる。レビューは `data/official-reviews/` に保存。

- Blue Note: https://www.bluenote.com/artist/norah-jones/
- Warner一覧: https://wmg.jp/miles-davis/discography
- Doo-Bop: https://wmg.jp/miles-davis/discography/18010 （WPCR-29228、2017-05-24再発）
- TUTU: https://wmg.jp/miles-davis/discography/19608 （WPJR-10030、2018-09-26再発）
- Sony日本一覧: https://www.sonymusic.co.jp/artist/MilesDavis/discography/ （通常取得403）
- Sony日本商品: https://www.sonymusic.co.jp/artist/MilesDavis/discography/SICP-10083 （通常取得403。検索エンジンの断片だけでは認定しない）

Sony／Columbia時代の全作品をWarner情報で補えるものではない。Sonyの取得については公式に利用できる資料・提供方法が確認できるまで既存の確認済み6作品を維持する。Warnerも現時点の一覧先頭12件のみ収集し、全ページ・全作品の網羅は保証しない。今回の12候補中、商品資料を照合して承認した2件だけを公開目次へ反映。残る10候補は未承認。

PR #18はマージ・Pages配信成功済み。この修正・追加は次のPRのマージ後に反映。

## v0.75：公式ページを個別レビューして増補

自動収集が制限される情報源は無効のまま、閲覧可能な公式作品資料の本文を個別に照合し、レビュー記録と目次データを同じPRに含める手動登録にも対応する。今回のColumbia主要18作品はこの方法。収集成功やページハッシュを偽って取込しない。

`data/official-reviews/miles-columbia-2026-10-27.json` は手動レビューの事実記録（オブジェクト形式）。`publish --reviews` に渡す承認配列ではない。直接HTTP取得の成功は未確認、無効ソースへの定期通信なし。作品リスト・根拠・検証は [V0.75-REVIEW.md](V0.75-REVIEW.md) を参照。v0.75の目次はノラ12、マイルス26、合計38作品となる。

## v0.76：作品ごとの手入力を不要にする共通生成経路

定期処理の主経路を候補保存から `scripts/generate_official_catalog.py` に移行。承認済みのプロバイダー共通ルールで名義・発売の根拠を検証して目次を生成し、テスト後に更新PRを作る。Blue Noteは公式アーティスト一覧からの名義発見にも対応。従来の候補収集・手動レビューCLIは残す。

設定、規則、定期PR、実取得結果、未対応範囲は [OFFICIAL-GENERATOR.md](OFFICIAL-GENERATOR.md) を参照。Sonyの取得制限は維持。今回のv0.76は共通生成による18作品追加、5アーティスト56作品。
