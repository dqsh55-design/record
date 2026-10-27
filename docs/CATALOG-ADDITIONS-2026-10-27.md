# v0.80：公式発売確認済み目次へ9作品追加

公開構成はGitHub Pagesだけを維持。ノラ・ジョーンズ1作品、マイルス・デイビス8作品を追加し、5組・56作品から5組・65作品へ更新する。コード変更はバージョン表示のみ。画像、配信リンク、サービス/API/DB、検索方式は追加・変更しない。

## 掲載する作品

| 名義 | 作品 | 表示年 | 確認元 |
| --- | --- | --- | --- |
| Norah Jones | Covers（カヴァーズ〜私のお気に入り） | 2012 | [Universal Music Japan公式商品](https://www.universal-music.co.jp/norah-jones/products/tocp-71410/)・[日本公式作品ページ](https://norahjones.jp/disco/tocp-71410/) |
| Miles Davis | Live-Evil | 1971 | [本人公式/Sony](https://www.milesdavis.com/albums/live-evil/) |
| Miles Davis | Big Fun | 1974 | [本人公式/Sony](https://www.milesdavis.com/albums/big-fun/) |
| Miles Davis | Dark Magus | 1977 | [本人公式/Sony](https://www.milesdavis.com/albums/dark-magus/) |
| Miles Davis | The Man With The Horn | 1981 | [本人公式/Sony](https://www.milesdavis.com/albums/the-man-with-the-horn/) |
| Miles Davis | We Want Miles | 1982 | [本人公式/Sony](https://www.milesdavis.com/albums/we-want-miles/) |
| Miles Davis | Star People | 1983 | [本人公式/Sony](https://www.milesdavis.com/albums/star-people/) |
| Miles Davis | Decoy | 1984 | [本人公式/Sony](https://www.milesdavis.com/albums/decoy/) |
| Miles Davis | You’re Under Arrest | 1985 | [本人公式/Sony](https://www.milesdavis.com/albums/youre-under-arrest/) |

ノラは12→13作品、マイルスは34→42作品。Bill Frisell4、Cannonball Adderley1、Ambrose Akinmusire5は変更なし。既存56作品の全フィールド（公式根拠・年・ID・直接リンク確認情報を含む）はそのまま保持する。

## 発売確認の根拠

マイルス8作品は公式作品ページの作品名、Release Date、Columbia RecordsのLabel、Recording Periodと音楽アルバムの曲目を個別照合した。録音年を発売年に使わない。Dark Magusの発売日は年のみ、1980年代5作品の発売日は月単位のため、存在しない日付を補わず原文と精度を保存し、画面では年だけを表示する。

ノラ『Covers』はUMJ公式商品のCD区分、本人名義、BLUE NOTE、国内発売日2012-10-31、品番TOCP-71410、10曲を確認。日本公式作品ページの英語題Coversと対応させた。UMJのオリジナル発売日2012.05.15と国内発売日は異なるため別々に記録し、共通の2012年のみ表示する。公式一覧ページの一括日付をこの作品の発売日に転用しない。

取得した公式HTMLのSHA-256、資料の発売表記、確認日、レビュー判断、対象名義を [レビューJSON](../data/official-reviews/catalog-expansion-2026-10-27.json) に保存する。これは公開資料の個別確認であり、全アーティストの自動収集の完成や、全作品網羅を意味しない。通常HTTPで取得できた資料を利用し、アクセス制限の回避は行っていない。日本公式CoversページはWeb取得で確認し、通常HTTPでは取得失敗したため、SHA-256は取得できたUMJ商品ページを記録した。

今回の追加作品はYouTube Musicの配信先を照合していないため、既存どおり検索へ案内する。公式発売が確認できたことと、YouTube Musicで配信・再生できることは区別する。『Visions』の確認済み直接リンクも変更しない。

## 保留・対象外

- Playing Along：今回読めたBlue Note資料は発売予告。発売後の公式商品資料の確認を完了していないため保留。
- First Sessions：6曲のデモ/短編作品。今回のアルバム追加では保留。
- Live At Ronnie Scott’s、Live In New Orleans等：公式の映像商品区分であり、音楽アルバムとして追加しない。
- The Little Willies、Puss N Boots等：別のバンド名義をノラ本人の目次へ混在させない。
- 既登録作品のデラックス版や形式違い：今回は独立した新作品として増やさない。

## 検証

追加9件とレビューの1対1対応、公式ホスト、名義、発売年・日付精度、音楽作品区分、全65作品の件数・重複なしを確認。追加分を除いた全56作品の指紋が変更前と一致することも確認する。

Pages画面テストはノラ13・マイルス42作品の表示、新規作品の公式根拠リンク、未照合配信先の検索維持、画像を追加していないことを確認。既存の直接リンク・保存・小画面・エラー処理・将来APIの回帰チェックも維持する。

本PRではマージや公開切替を行わず、修正・テスト・PR作成までを実施する。
