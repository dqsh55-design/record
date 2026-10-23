# YouTube Music接続調査（2026-10-23）

PR #2の追加調査。マージ、公開反映、カタログ更新workflowの起動は行っていません。
実測記録は [matching-diagnostic-2026-10-23.json](matching-diagnostic-2026-10-23.json)。このJSONは診断専用で、画面が読むカタログではありません。

## 切り分け結果

- クラウドの設定上は `music.youtube.com`、`musicbrainz.org`、`coverartarchive.org` が許可対象。runtimeのpolicy stateは `unknown` であり、許可設定が正常に適用された証明にはならない。
- 通常sandboxではソケット接続自体が拒否される。必要な実行権限で、継承した `http://proxy:8080` 経由・TLS検証を有効にして再確認。
- curlのHEAD、Python標準ライブラリのHEAD、ytmusicapiのアルバム詳細取得のいずれも、YouTube Music宛CONNECTで403。curlは `CONNECT tunnel failed, response 403`、プロキシ応答は `server: envoy`。TLSトンネル確立前であり、YouTube側のHTTP 403・ログイン不足・地域制限・レスポンス解析失敗とは判定できない。
- 同じプロキシでMusicBrainzはHEADと検索・発売盤詳細取得に成功。プロキシ全体の停止ではなく、接続先によって結果が異なる。
- `ytmusicapi 1.12.3` でも同じCONNECT拒否。ライブラリ変更やCookie投入では解消しない。1.12.3の `get_album` と `parse_album_header_2024` の実装には、構造化した `label` / `publisher` の抽出がない。接続が直っても現行の全項目一致条件ではレーベルが不足する見込み。実レスポンスを取得できたとの主張はしない。
- providerの保持診断は `not_found`。403を返す内部ルール・上流制約の正確な理由は未特定。設定側の許可漏れと断定しない。

直接接続、プロキシ解除、別ホストへの転送、第三者プロキシ、Cookieの流用、アクセス拒否を避けるスクレイピングは行っていません。

## 実アルバムの確認

|対象|MusicBrainzで実取得した発売盤の例|レーベル・曲数|YouTube Musicとの判定|
|---|---|---|---|
|Jeff Beck / Blow by Blow|[1975年GB盤](https://musicbrainz.org/release/496a1856-c8ac-3a4b-8415-a6610250cfd7)|Epic・9曲|情報不足：YouTube側未取得|
|Jeff Beck / Best of Beck|[1995-08-15 US盤](https://musicbrainz.org/release/f7b16126-1638-418d-932b-edfa90d5da0e)|Epic・14曲|情報不足：YouTube側未取得|
|Miles Davis / Kind of Blue|[1987年US盤](https://musicbrainz.org/release/e32a3f0b-1c19-3170-bb1c-650893774744)|Columbia・5曲|情報不足：YouTube側未取得|

MusicBrainzのOfficial登録を取得したもので、YouTube配信盤の正規性を確認した結果ではない。検索ヒットは順に26件・1件・126件、診断では最大3発売盤ずつ詳細を取得。Kind of Blueには19曲盤・6曲盤もあり、作品名だけでは同一発売盤を選べない。対象のYouTubeアルバムIDは既存カタログから採用し、今回は全3件で実詳細を取得できなかった。曲数・曲目はMusicBrainzの同一発売盤の詳細から取得し、YouTubeの欠落情報を補完した一致判定は作っていない。

## 利用可能な取得方法と推奨手順

1. 現環境ではMusicBrainzの公開Web Serviceを利用できる。1.1秒間隔、出典付きで候補と曲目を調査できる。既存YouTubeリンク・保存記録・カタログを維持し、未取得を情報不足とする運用は可能。
2. クラウド環境の管理側で、設定済みプロキシから `music.youtube.com:443` へのCONNECTが403になる理由を確認する。必要なのはサポートされたネットワーク設定・提供側の許可であり、コードによる迂回ではない。現状は認証情報を追加する根拠がない。継承プロキシ・CA・TLS検証を維持する。
3. 規約に沿った自動取得の候補は公式YouTube Data API v3。Google CloudプロジェクトでAPIを有効化し、制限付きAPIキーまたは必要な権限のOAuth、クォータ、承認済み接続先（使用する公式クライアントに応じて `www.googleapis.com` / `youtube.googleapis.com` 等）の設定が必要。現在の環境にはそれらの認証設定・明示的な接続先許可がない。公開playlistItems/videosは曲目の補助候補だが、YouTube Musicのbrowse ID・発売盤レーベル・正規配信権利を保証するAPIではない。検索順位やチャンネル名を正規性の根拠にしない。公式APIの仕様・条件は [概要](https://developers.google.com/youtube/v3/getting-started)、[playlistItems](https://developers.google.com/youtube/v3/docs/playlistItems/list)、[開発者ポリシー](https://developers.google.com/youtube/terms/developer-policies) を参照。今回はこれらの接続を試していない。
4. 公開ページで見える情報も自動取得の許可とは同義でない。ytmusicapiは非公式のため、その利用だけで規約適合を保証しない。新しいHTMLスクレイピング方式や別の非公式エンドポイントへの切替は追加していない。正式な提供元・レーベルの許諾済みフィードや、利用者が通常の画面で確認した出典付き記録を補助にできるが、欠損フィールドは欠損のまま扱う。
5. 接続と利用条件を確認後、まず下記の診断を再実行し、3作品について同一発売盤の全アーティスト・レーベル・全曲・曲順をレビューする。レーベルが不足すれば情報不足を維持する。成功確認後にPR内でカタログ更新結果をレビューし、公開可否を別途判断する。

## 再実行と変更範囲

```sh
pip install 'ytmusicapi>=1.10,<2'
python scripts/diagnose_matching.py --output work/matching-diagnostic.json
python -m unittest discover -s tests -p 'test_*matching.py' -v
node tests/test_browser.cjs
python tests/test_ui.py
```

診断はYouTube取得失敗時もMusicBrainzを独立調査し、例外本文や認証情報を出力しない。`data/` への診断出力を拒否する。実アプリの検索・保存・リンク・画面・カタログJSONは変更していない。既存の読み取り専用確認workflowに対象3作品の診断artifactを追加した。workflowは手動実行のままで、今回起動していない。

検証：Python 30件、JavaScript回帰、Python構文チェック、差分チェックを通過。画面回帰結果はMATCHING.mdの追記を参照。テスト用の外部API応答は実データ照合の成功根拠に使用しない。
