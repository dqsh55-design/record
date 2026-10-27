# v0.84：ジャンルを広げる9組・18作品

2026-10-27、AGENTS.mdの公式発売掲載基準に従い、既存5組100作品をそのまま保って9組18作品を追加。目次は14組118作品。B’zは今回の対象外。

本人・レコード会社の公式掲載を発売確認の根拠とし、MusicBrainzでの二重認定を行わない。各組の代表作2作品を掲載する範囲から始め、全ディスコグラフィーを網羅したとは扱わない。

| アーティスト | 作品 | 表示年 | 公式発売情報 |
| --- | --- | --- | --- |
| The Beatles | Abbey Road | 1969 | [The Beatles Official Site](https://www.thebeatles.com/abbey-road) |
| The Beatles | Revolver | 1966 | [The Beatles Official Site](https://www.thebeatles.com/revolver) |
| Led Zeppelin | Led Zeppelin II | 1969 | [Led Zeppelin Official Discography](https://discography.ledzeppelin.com/lz2) |
| Led Zeppelin | Led Zeppelin IV | 1971 | [Led Zeppelin Official Discography](https://discography.ledzeppelin.com/lz4) |
| Black Sabbath | Paranoid（パラノイド） | 1970 | [Universal Music Japan](https://www.universal-music.co.jp/p/uicy-20039/) |
| Black Sabbath | Master of Reality（マスター・オブ・リアリティ） | 1971 | [Universal Music Japan](https://www.universal-music.co.jp/p/uicy-20106/) |
| Metallica | Master of Puppets | 1986 | [Metallica Official Site](https://www.metallica.com/releases/albums/master-of-puppets-album.html) |
| Metallica | Metallica | 1991 | [Metallica Official Site](https://www.metallica.com/releases/albums/the-black-album.html) |
| Kraftwerk | Autobahn（アウトバーン） | 1974 | [Warner Music Japan](https://wmg.jp/kraftwerk/discography/11358) |
| Kraftwerk | Computer World（コンピューター・ワールド） | 1981 | [Warner Music Japan](https://wmg.jp/kraftwerk/discography/11362) |
| Daft Punk | Discovery | 2001 | [Daft Punk Official Site](https://daftpunk.com/discovery/) |
| Daft Punk | Random Access Memories | 2013 | [Daft Punk Official Site](https://www.daftpunk.com/randomaccessmemories/) |
| David Bowie | Hunky Dory（ハンキー・ドリー） | 1971 | [Warner Music Japan](https://wmg.jp/davidbowie/discography/11404) |
| David Bowie | The Rise and Fall of Ziggy Stardust（ジギー・スターダスト） | 1972 | [Warner Music Japan](https://wmg.jp/davidbowie/discography/11405) |
| Michael Jackson | Thriller | 1982 | [Sony Music Japan](https://www.sonymusic.co.jp/artist/MichaelJackson/page/bscd2_2016) |
| Michael Jackson | Bad | 1987 | [Sony Music Japan](https://www.sonymusic.co.jp/artist/MichaelJackson/page/bscd2_2016) |
| Ryuichi Sakamoto | async | 2017 | [commmons](https://www.commmons.com/archive/whatsnew/artists/sakamotoryuichi/202310060910.html) |
| Ryuichi Sakamoto | 12 | 2023 | [commmons](https://www.commmons.com/archive/carbonoffset/2023/015630.html) |

## 発売情報の扱い

- 発売年は公式資料に明記された作品年を優先。Black Sabbath、Kraftwerk、asyncの作品年と日本盤再発日を分け、坂本龍一『12』の曲名に含まれる制作年を発売年にしない。
- Bowieの初回作品年は本人公式の発売記念記事で補足し、Warner掲載の2014年日本盤発売日と分離。補足URLはレビュー記録に保持。
- レーベル欄は、公式資料で確認したレーベルまたは現行の発売情報掲載元を表示する。BeatlesのEMIはUniversalの掲載盤、MetallicaのBlackened Recordingsは現行公式の権利表記、Led ZeppelinのRhino Entertainmentは現行公式ディスコグラフィー提供元を示す。初版レーベルを推測した値ではない。
- Michael JacksonはSonyの公式発売一覧と本人公式アルバム頁を検索サービス経由で確認。直接HTML取得は403のため終了し、制限回避は行っていない。取得方法・照合事実・照合事実のSHA256を記録し、取得していない原文HTMLのハッシュは付けない。Sonyの一覧ではMichael本人とThe Jacksonsの掲載欄を区別。
- ほかの追加作品は公式HTMLの取得SHA256をレビューに記録。取得失敗は未発売・未配信の根拠にしない。

## YouTube Music

[Daft Punk本人公式Discovery](https://daftpunk.com/discovery/) → [公式配信案内](https://daftpunk.lnk.to/Discovery) → [YouTube Music](https://music.youtube.com/playlist?list=OLAK5uy_mz6eafmqdRHSaR4IwG0ll6J6rgv0_ZpGw) を確認。作品名Discovery、名義Daft Punk、music.album、自己一致するcanonicalを取得し、この1作品に直接リンクを追加した。案内の追跡パラメーターは外し、取得先のcanonicalを使う。ログイン後の再生、地域別配信可否は未検証。

Beatles『Abbey Road』は公式案内の表示がRemasteredでも到達先がSuper Deluxe Editionだったため、今回の通常作品には直接リンクを登録しない。『Revolver』もリマスター版との照合を完了した扱いにせず検索方式を維持。Metallica2作品、Daft Punk『Random Access Memories』、坂本龍一『async』、Led Zeppelin IVの確認した公式案内にはYouTube Musicアルバムのリンクが見つからなかった。未配信とは断定しない。ほかの新規作品も直接リンク未確認のため検索へ案内する。

既存の3直接リンクと全作品の検索URL生成処理を維持。配信未確認でも公式発売が確認できた18作品を掲載する。

## 構成と回帰検証

GitHub Pagesのみ。新サービス・API・DB・画像の追加なし。v0.83の開閉式根拠表示、検索、対応アーティストボタン、保存記録・バックアップを維持。検索時に公式サイトへアクセスせず、同梱JSONを再利用するため公式サイトの負荷を増やさない。

既存100作品の全フィールド・既存アーティスト情報の指紋比較、18作品の根拠との整合、重複、年、取得方法、直接リンクと見送り理由、9組の日英別名、許可ホストの偽装拒否をテスト。320/390/430pxの全作品情報・リンク不変・根拠開閉に加え、追加9組の日本語検索とB’z対象外をブラウザ回帰する。公開反映とiPhone実機Safari確認はPRテストとは別に扱う。

照合記録: [artist-expansion-2026-10-27.json](../data/official-reviews/artist-expansion-2026-10-27.json)
