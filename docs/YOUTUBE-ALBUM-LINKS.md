# v0.79：確認できた配信リンクだけアルバムへ直接案内

2026-10-27。GitHub Pagesのまま、公開作品カードのリンク処理だけを改善する。外部サービス登録、API/DB追加、検索方式の変更は行わない。

## 変更

公開中の`renderOfficialCatalog`は、以前の直接リンク処理を参照せず、全作品でYouTube Music検索URLを生成していた。旧`recordVerifiedLinks`は利用者が登録した未照合URL、旧配信目次は名称一致のみの候補を含むため、それだけで直接リンクには昇格させない。既存の厳密なYouTube MusicアルバムURL検証・正規化・名義照合関数を再利用する。

既存`data/official-catalog.json`の作品に、別途確認した`listeningLink`を付ける。公式発売の確認とは独立した根拠であり、直接リンクの有無で作品の掲載可否や公式発売の証拠を変更しない。

直接案内の条件:

- 作品が既存の公式発売確認条件を満たす。
- 作品ID・アーティストID・作品名・公式発売の根拠URLが一致。
- 公式ページから案内される配信ページのURLと作品/名義の見出しを確認。
- その配信ページのYouTube Musicリンクと到達先canonical URLが一致。
- YouTube Music側が`music.album`で、作品名・本人名義（既存の日本語別名も可）が一致。
- 確認日、確認内容、取得HTMLのSHA-256を保持。
- URLはHTTPSのYouTube Musicアルバムだけ。動画、検索、チャンネル、利用者作成プレイリスト、別ホスト、認証情報・ポート・不要なパラメーター等は拒否。

条件が欠けたり相違した場合は従来の検索URLを使う。利用者の保存URLを上書きしたり、未照合URLを自動採用したりしない。直接案内できるカードにも検索リンクを残し、地域制限や後日の配信変更に備える。公式発売の根拠リンクと資料確認日もそのまま維持する。

## 実通信での確認結果

| 作品 | 今回の扱い | 確認内容 |
| --- | --- | --- |
| Norah Jones / Visions | 直接リンク | Blue Note本人ページ→Norah Jones公式配信案内→YouTube Musicのアルバム。作品名・本人名義・canonicalを確認 |
| Norah Jones / Pick Me Up Off The Floor | 検索を維持 | 公式案内先にYouTube Musicリンクはあるが、到達先は日本語題。今回の単純な作品名一致を拡張せず保留 |
| Norah Jones / The Fall、Begin Again | 検索を維持 | 取得できた公式配信案内には、採用条件に適合するYouTube Musicアルバムリンクがない（動画や一般プレイリストは採用しない） |
| Miles Davis / Kind Of Blue | 検索を維持 | 旧候補のYouTube Musicページは作品名・名義を確認できたが、公式配信案内から同じ到達先を結び付けられず保留 |
| その他の作品 | 検索を維持 | 今回、直接案内に必要な確認を完了していない |

『Visions』の確認経路:

1. https://www.bluenote.com/artist/norah-jones/
2. https://norahjones.lnk.to/Visions
3. https://music.youtube.com/playlist?list=OLAK5uy_lM3P4kceusY0iTd2n-RzLeqUKHHc_fMxo

上記3ページを通常のHTTP取得で確認。配信案内の追跡用パラメーターを除き、到達先が示すcanonical URLの`list`値をそのまま採用した。リンク先の日本語名義「ノラ・ジョーンズ」は既存のNorah Jones別名と一致する。実際のログイン後再生や日本の利用者ごとの配信可否を確認したという意味ではなく、再生開始も保証しない。

マイルスの公式ページ https://www.milesdavis.com/albums/kind-of-blue/ にYouTube Music向けの案内はあるが、取得した https://milesdavis.lnk.to/KOBAW/youtubemusic!discog では採用できるYouTube MusicアルバムURLを確認できなかった。旧候補URLを推測で補わず、検索を維持する。

## 検証

- ノラ12・マイルス34作品の公式掲載条件と件数を維持。
- 確認済み直接リンク、誤名義・作品名・出典・確認日・資料ハッシュ・対象種別・不正URL・欠けた確認情報の拒否をNodeで確認。
- Pages画面で『Visions』の直接リンクをクリックし、同じアルバムURLへの別タブ遷移を確認。公式根拠と検索リンクの維持も確認。クリックテストの遷移先はテスト用に応答し、実再生テストとは区別する。
- ノラの未照合作品とマイルス『Kind Of Blue』は検索URLを維持することを確認。
- 既存の小画面、未対応、取得失敗、保存記録、将来APIの回帰テストも継続。

取得制限の回避や新しい常駐サービスは使用しない。確認済み情報は静的JSONに保存するため、利用者の検索時に配信先へ照合通信を追加しない。
