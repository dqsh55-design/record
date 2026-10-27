# 公式ディスコグラフィーの継続追加

公開目次は引き続き `data/official-catalog.json` のみ。収集結果は公開に使用しない。

## 定期取得

`Collect official discography candidates` は毎週月曜12:25 JSTと手動実行に対応。
`data/official-sources.json` のBlue Note（ノラ）、Sony運営マイルス公式を取得し、Actionsの `official-discography-candidates` 成果物に候補JSONを90日保存する。書き込み権限なし、目次への自動認定なし。取得日時、ページハッシュ、件数、HTTP失敗、抽出0件（構造変更の疑い）を記録する。失敗時も成果物を保存しジョブを失敗として通知する。各実行は独立したスナップショット。前回成果物を自動ダウンロードしない。

Blue Noteはrelease-entry内の作品見出しを抽出し、バンドとの複合名義を除外する。外部販売リンクを根拠URLにしない。マイルスは同一ホストの /albums/作品/ リンクを候補化する。候補だけでは作品種別やレーベルを保証しない。ページ送りは未対応なので全件網羅とはしない。

## レビューと追加

1. `python scripts/official_discography.py collect --report reports/official-candidates.json`
2. 各公式資料で作品名・本人名義・アルバム種別・発売元を確認。作品単位の確認であり、個別再発盤やYouTube配信の認定には使わない。
3. レビューJSONを作成（次の例のIDは候補JSONからコピー）。資料が不十分ならrejectまたは未登録のままにする。発売年不明ならnull。

```json
[
  {
    "candidateId": "候補のid",
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

承認のない候補は追加されない。重複作品はスキップ、既存ID・確認日・根拠は維持。不正レビューが一件でもあれば全体を中止し、ファイルを置換しない。取得失敗源の承認も拒否。既存作品の削除や出典の自動更新はしない。アーティスト追加時は公開目次に名義・別名・空albumsと、公式sources設定をPRで追加する。新ホストはブラウザ側officialSourceHostsの追加レビューも必要。

## 検証（2026-10-27 JST）

新規7テスト、Python既存32件、Node既存全7スイートが成功。実ページ取得ではBlue Noteのノラ12候補を抽出。マイルス一覧はHTTP 403となり実取得の成功は未確認。定期実行はこのPRのマージ後から有効。取得障害を回避して未確認データを掲載する処理はない。公開目次の作品数は今回変更しない。
