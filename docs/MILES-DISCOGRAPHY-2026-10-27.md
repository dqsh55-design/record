# v0.81：マイルスの公式ディスコグラフィーから12作品追加

AGENTS.mdを作業前に読み、**レコード会社または本人公式サイトに発売作品として掲載されていること**を正規盤の基準として適用した。MusicBrainz等の二重認定は行わず、配信リンクの可否を掲載条件にしない。AGENTS.md自体は変更していない。

## 追加する作品

[本人公式のReleases](https://www.milesdavis.com/music/releases/)から各作品ページを辿り、既存42作品との重複がない12件を確認した。

| 作品 | 公式ページに記載された発売日 | 表示レーベル | 公式根拠 |
| --- | --- | --- | --- |
| Birth Of The Cool | Feb, 1957 | Blue Note (BLU) | https://www.milesdavis.com/albums/birth-of-the-cool/ |
| Walkin' | 1957 | Prestige | https://www.milesdavis.com/albums/walkin/ |
| Cookin' With The Miles Davis Quintet | Jul, 1957 | Prestige | https://www.milesdavis.com/albums/cookin-with-the-miles-davis-quintet/ |
| Relaxin' With The Miles Davis Quintet | Mar, 1958 | Prestige | https://www.milesdavis.com/albums/relaxin-with-the-miles-davis-quintet/ |
| Workin' With The Miles Davis Quintet | Dec, 1959 | Prestige | https://www.milesdavis.com/albums/workin-with-the-miles-davis-quintet/ |
| Steamin' With The Miles Davis Quintet | Jul, 1961 | Prestige | https://www.milesdavis.com/albums/steamin-with-the-miles-davis-quintet/ |
| Bags' Groove | 1957 | Prestige | https://www.milesdavis.com/albums/bags-groove/ |
| Quiet Nights | Dec 16, 1963 | Columbia Records | https://www.milesdavis.com/albums/quiet-nights/ |
| Miles In Tokyo | Jun 6, 1969 | Columbia Records | https://www.milesdavis.com/albums/miles-in-tokyo/ |
| Miles In Berlin | Feb 1, 1965 | Columbia Records | https://www.milesdavis.com/albums/miles-in-berlin/ |
| In Europe | Jul 13, 1964 | Columbia Records | https://www.milesdavis.com/albums/in-europe/ |
| Miles Davis At Carnegie Hall | Jul 16, 1962 | Columbia Records | https://www.milesdavis.com/albums/miles-davis-at-carnegie-hall/ |

マイルス42→54作品、目次全体65→77作品。ほかの4名義は変更しない。既存65作品の全項目・直接リンク・公式根拠はそのまま保持する。

レーベルは公式作品ページの現在の表示を記録し、別資料から初版レーベルを推測して上書きしない。Birth Of The Coolも公式ページ表記のBlue Note (BLU)をそのまま採用する。表示年はRelease Dateから採用し、録音年と区別する。Miles In Tokyoは録音期間が1964年でも、公式ページの発売日1969年を記録する。月/年単位の発売日に架空の日付を補完しない。

[レビューJSON](../data/official-reviews/miles-discography-2026-10-27.json)に、公式一覧・作品のURL、取得HTMLのSHA-256、確認日、表示用情報、正規盤判断の基準を保存した。これらの発売日・曲目・レーベルは表示用の確認情報であり、公式発売作品として掲載されていることに追加の外部認定を課すものではない。

## YouTube Music

Birth Of The Coolは公式ページのYouTube Music向け配信案内を辿り、配信案内のURLと到達先canonical、アルバム名、本人の日本語名義、music.albumが一致した。

- 公式作品: https://www.milesdavis.com/albums/birth-of-the-cool/
- 公式からの配信案内: https://milesdavis.lnk.to/BirthOfTheCoolAW/youtubemusic!discog
- 確認したアルバム: https://music.youtube.com/playlist?list=OLAK5uy_nfPW5nyULUfkW0ve_spRRuc4ZYh8Gjm-I

既存の確認済みリンク方式へ情報を追加し、直接開けるようにする。現在の地域別配信やログイン後の実再生を検証したとは扱わない。直接リンクのカードにも検索の代替導線を維持する。

Quiet Nightsの公式配信案内は取得失敗だったため、推測でURLを登録せず検索へ案内する。この失敗を公式発売作品の掲載不可とは扱わない。ほかの新規作品も直接リンク未確認として検索方式を維持する。既存のNorah Jones / Visionsの直接リンクは変更しない。

## 構成・検証

GitHub Pagesのみ。新たなサービス/API/DB/ジャケット画像を追加せず、アプリの処理は変更していない（バージョン表示のみ更新）。通常の公開資料閲覧で確認し、アクセス制限回避はしない。

- 新規12作品とレビューの対応、公式出典、重複なし、発売年と録音年の区別を検証。
- 追加分を除く目次全体の指紋一致により、既存65作品の全情報の保持を検証。
- 正規発売判断と直接リンク可否を分離し、配信先取得失敗のQuiet Nightsも掲載されることを検証。
- Pages画面で日本語検索、マイルス54作品、新規12件の公式根拠、Birth Of The Coolの直接URL、ほかの検索案内、画像なしを確認。
- 既存の保存記録・公式根拠・Visions直接リンク・未対応/通信失敗・小画面・将来APIの回帰テストも継続。

このPRの範囲は修正・テスト・PR作成まで。本番公開や利用者のiPhoneでの実再生確認とは分けて報告する。
