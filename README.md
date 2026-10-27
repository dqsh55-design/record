# RECORD

公式資料で正規発売を確認したアルバムから、YouTube Musicで聴く作品を探すための目次です。

**現在の公開構成はGitHub Pagesだけ。外部サービスへの登録、検索API、サーバー、データベースは不要です。**

アーティスト名を日本語・英語で検索するか、対応アーティストのボタンを選択します。公開目次は14組・118作品。発売の根拠となる公式URLと資料確認日を表示し、確認済みのアルバムリンク、またはYouTube Music検索へ案内します。配信や再生の可否は別途確認が必要です。

利用者の検索時に公式サイトやMusicBrainzへ情報取得を行いません。未対応のアーティストは、公開中の目次で確認できない旨を表示します。公式サイトや作品が存在しないとは判断しません。

- [v0.83のスマートフォン向け一覧](docs/MOBILE-CATALOG.md)
- [v0.84の追加9組・18作品と根拠](docs/ARTIST-EXPANSION-2026-10-27.md)
- [現在の設計・公開手順](docs/PAGES-FIRST.md)
- [確認済み配信リンクの条件と検証結果](docs/YOUTUBE-ALBUM-LINKS.md)
- [v0.80の追加作品と根拠](docs/CATALOG-ADDITIONS-2026-10-27.md)
- [v0.81のマイルス追加作品と配信リンク](docs/MILES-DISCOGRAPHY-2026-10-27.md)
- [v0.82の100作品への追加と根拠](docs/CATALOG-HUNDRED-2026-10-27.md)
- [公式目次](data/official-catalog.json)
- [将来の任意API](server/README.md)

ローカル確認は `python -m http.server 8000` をリポジトリのルートで実行し、http://localhost:8000/ を開いてください。静的ファイルの確認用であり、本番のPythonサーバー導入は必要ありません。
