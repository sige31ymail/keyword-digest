# keyword-digest

GitHub の Issue に「気になったキーワード」を登録しておくと、GitHub Actions が定期的に
AI（OpenAI 主 / Anthropic フォールバック）でそのキーワードに関するレポートを生成し、
**RSS フィード + HTML ページ**として GitHub Pages に公開するバックエンドです。

公開されたフィードは、オフラインニュースリーダー **PocketDigest** にソースとして追加するだけで
記事として閲覧できます（PocketDigest 側の改修は不要）。

```
[GitHub Issue (=キーワード)]
        │  Open な Issue を取得
        ▼
[GitHub Actions (cron 1日1回 / 手動実行)]
        │  OpenAI 主・Anthropic フォールバックでレポート生成
        ▼
[site/reports/<date>-<slug>.html] + [site/feed.xml]
        │  GitHub Pages で公開
        ▼
[PocketDigest が feed.xml を購読 → オフライン閲覧]
```

## 使い方（概要）

1. このリポジトリを GitHub に作成し、Pages を有効化する。
2. リポジトリの Secrets に `OPENAI_API_KEY`（必須）と `ANTHROPIC_API_KEY`（任意・フォールバック）を登録する。
3. Issue に調べたいキーワードをタイトルとして登録する（本文に観点や粒度の指示を書くと反映される）。
4. Actions の `Generate Reports` を手動実行（または毎日の cron を待つ）。
5. 公開された `https://<owner>.github.io/keyword-digest/feed.xml` を PocketDigest のソースに追加する。

## ローカル実行（生成物を `site/` に書き出すだけ・公開はしない）

```bash
export OPENAI_API_KEY=sk-...
export GITHUB_REPOSITORY=<owner>/keyword-digest   # Issue 取得先
export GITHUB_TOKEN=ghp_...                        # Issue 読み取り用
export SITE_BASE_URL=https://<owner>.github.io/keyword-digest
python -m src.main
```

設計の詳細は [docs/ddd-design.md](docs/ddd-design.md) を参照。
