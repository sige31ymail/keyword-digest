# keyword-digest DDD設計書

## 0. 概要・目的

GitHub の Issue に登録した「気になったキーワード」について、AI（OpenAI 主 / Anthropic フォールバック）が
定期的にレポートを生成し、**RSS フィード + HTML ページ**として GitHub Pages に公開するバックエンド。

公開フィードは PocketDigest（オフラインニュースリーダー）に **ソース追加するだけ**で閲覧できる。
本書は memo-android-app / PocketDigest の `DDD設計書.md` と同じ様式に倣う。

**今回のスコープ**: GitHub リポジトリに手動で Issue（=キーワード）を登録し、AI がレポートを生成・配信するところまで。
memo-android-app からの自動 Issue 登録、PocketDigest 本体の改修は後続。

確定方針: 配信は RSS フィード方式 / 生成 AI は OpenAI 主・Anthropic フォールバック / 1日1回実行。

技術的前提（PocketDigest 調査より）: PocketDigest はフィードから **タイトル・URL・公開日時のみ**を読み、
本文は記事 URL の HTML を `SimpleArticleTextExtractor` で抽出する（`<article>`/`<main>`/`<body>` 配下の
`<h1-6>`/`<p>`/`<li>` 等、最小 120 文字）。よって各レポートを **HTML ページ + それを指す RSS フィード**として
公開すれば PocketDigest は無改修で読める。

---

## 1. ユビキタス言語

| 用語 | 定義 |
| --- | --- |
| キーワード (Keyword) | 利用者が関心を持つテーマ。GitHub Issue のタイトル。 |
| キーワード補足 (Keyword Note) | Issue 本文。生成プロンプトへの追加指示（観点・粒度）。任意。 |
| キーワード登録 | Issue を作成すること（今フェーズは手動）。Open=生成対象、Close=停止。 |
| レポート (Report) | あるキーワードについて AI が生成した日本語記事。集約ルート。 |
| 生成ラン (Generation Run) | cron / 手動による 1 回の実行単位。複数キーワードを処理。 |
| レポートジェネレータ | キーワード→レポートを生成するポート。OpenAI / Anthropic 実装。 |
| フィード (Feed) | 配信用 RSS（feed.xml）。直近 N 件のレポートを列挙。 |
| 配信サイト (Publish Site) | GitHub Pages で公開する `site/` 一式（feed.xml + 各レポ HTML）。 |
| 抽出可能性 (Extractability) | PocketDigest が本文抽出できる条件（`<article>` 構造・最小 120 文字）を満たすこと。 |

---

## 2. 境界づけられたコンテキスト

| コンテキスト | 責務 | 本フェーズ |
| --- | --- | --- |
| レポート生成コンテキスト | キーワード取得→AI生成→HTML/RSS化→Pages公開 | ◎ 今回 |
| キーワード登録コンテキスト | memo-android-app からの Issue 自動作成 | 後続 |
| 閲覧コンテキスト | PocketDigest によるフィード購読・閲覧 | 後続（手動ソース追加で検証） |

---

## 3. ドメインモデル

### 集約ルート: Report
```
Report
├ id: ReportId              … date + slug
├ keyword: Keyword
├ title: ReportTitle        … 一覧/フィード用タイトル
├ body: ReportBody          … 段落リスト（抽出可能性を内包）
├ generated_at: datetime
└ generated_by: GenerationModel  … openai / anthropic
不変条件: body は抽出可能性（最小120文字・段落1つ以上）を満たす。
```

### 値オブジェクト
| 名前 | 制約 |
| --- | --- |
| Keyword | 非空・前後トリム。Issue タイトル由来。 |
| KeywordNote | 任意。Issue 本文由来。 |
| ReportId / ReportSlug | `YYYYMMDD-<ascii>-<hash8>`。URL・ファイル名・GUID。日付込みで日次ユニーク、同一キーワード同日は安定（再実行で上書き）。 |
| ReportTitle | 一覧用 1 行タイトル。 |
| ReportBody | 段落 `list[str]`。HTML の `<p>` に対応。 |
| GenerationModel | `openai` / `anthropic`。 |

### エンティティ（診断用・任意）: GenerationRun
`trigger / started_at / keyword_count / succeeded / failed / fallback_used`。
PocketDigest の `refresh_runs` と同思想。Phase 4 で導入（当初はログ出力）。

---

## 4. ドメインサービス

| サービス | 責務 |
| --- | --- |
| ReportSlugFactory | `(date, keyword) → ReportSlug`。日本語キーワードを ASCII 化 + md5 ハッシュで URL 安全化。 |
| ReportContentPolicy | 本文が抽出可能性（最小120文字・段落あり）を満たすか検証。失敗時は生成失敗扱い。 |
| FeedAssembler | 既存レポート群から直近 N 件の Feed を組み立てる純粋ロジック。 |
| ReportRetentionPolicy | 期間（max_age_days）+ 件数（max_count）の併用で保持/削除を判定。古いか件数超過のいずれかで削除。PocketDigest の `PruneOfflineLibraryUseCase`（期限/件数ベース整理）と対称。保持件数 ≧ フィード掲載件数を保証しリンク切れを防ぐ。 |

---

## 5. ポート

| ポート | 役割 | 実装（Phase） |
| --- | --- | --- |
| `KeywordSource` | Open Issue 一覧 → `list[Keyword]` | GitHubIssueKeywordSource（P1） |
| `ReportGenerator` | `Keyword → Report` 生成 | OpenAi（P1）/ Anthropic（P3）/ Fallback（P3） |
| `SitePublisher` | HTML + feed.xml の書き出し・既存走査・削除 | StaticSitePublisher（P2）。公開は Actions の deploy-pages |

---

## 6. アプリケーションサービス

### GenerateDailyReportsUseCase（中核）
```
1. keywords = KeywordSource.list_open()
2. for each keyword:
     try:
       report = ReportGenerator.generate(keyword)   # 主OpenAI、失敗時Anthropic
       ReportContentPolicy.validate(report.body)
       SitePublisher.write_report_page(report)        # reports/<slug>.html
     except: 記録して次へ（1件の失敗を全体に波及させない）
3. existing = SitePublisher.list_existing_items()      # 蓄積済み(checkoutで取得) + 今回分
4. keep, remove = ReportRetentionPolicy.partition(existing, now, max_age_days, max_count)
   SitePublisher.delete_reports(remove)                # 古い/超過レポートを削除
5. feed = FeedAssembler.assemble(keep, max_feed_items) # 保持分から直近 N 件
   SitePublisher.write_feed(feed)                      # feed.xml + index.html
6. （Actions が site/ をコミット&push して蓄積 → Pages へデプロイ）
7. GenerationRun を集計してログ出力
```

**蓄積（永続化）**: `site/` はリポジトリで追跡し、ワークフローが毎回 `git add site && commit && push`
する。`checkout` で過去レポートを取り戻し、保持ポリシーで一定量に保つ。フィード窓（`max_feed_items`=20）
＜ 保持窓（`max_count`=100, `max_age_days`=30）として、フィード掲載リンクが必ず実在するようにする。

---

## 7. インフラ層

PocketDigest の軽量方針（重い依存を避ける）を踏襲し、**Python 標準ライブラリのみ**で実装
（urllib / json / xml / hashlib）。外部 SDK・テンプレートエンジンは不使用。

| 実装 | 技術 |
| --- | --- |
| GitHubIssueKeywordSource | REST `GET /repos/{owner}/{repo}/issues?state=open`（PR を除外） |
| OpenAiReportGenerator | OpenAI Chat Completions（`gpt-4o-mini`）, `response_format=json_object` |
| AnthropicReportGenerator | Anthropic Messages（`claude-haiku-4-5`） |
| FallbackReportGenerator | 主失敗時に副へ切替（PocketDigest `FallbackAiEnrichmentClient` と同思想） |
| StaticSitePublisher | 文字列テンプレで HTML、手組みで RSS 2.0。`<meta name="kd:*">` でメタ情報を埋め、再実行時に既存レポートを復元。`delete_reports` で保持ポリシー削除を実行 |

Secrets（Actions）: `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GITHUB_TOKEN`（自動）。
環境変数: `MAX_FEED_ITEMS`(20) / `RETENTION_MAX_AGE_DAYS`(30) / `RETENTION_MAX_COUNT`(100)。
ワークフロー権限は蓄積コミットのため `contents: write`。

---

## 8. 配信フォーマット仕様（PocketDigest 互換の要）

### レポート HTML（site/reports/<slug>.html）
```html
<article>
  <h1>{title}</h1>
  <p>{paragraph1}</p>
  <p>{paragraph2}</p>
</article>
```
`SimpleArticleTextExtractor` が `<article>`+`<p>` を抽出。**本文 120 文字以上**必須。広告/スクリプトは含めない。

### RSS（site/feed.xml, RSS 2.0）
```xml
<item>
  <title>{title}</title>
  <link>https://<owner>.github.io/keyword-digest/reports/<slug>.html</link>
  <guid isPermaLink="true">...<slug></guid>
  <pubDate>{RFC822}</pubDate>
</item>
```
PocketDigest は title/link/pubDate のみ使用。直近 N 件（既定 20）を列挙。

---

## 9. ディレクトリ構成

```
keyword-digest/
├ .github/workflows/generate-reports.yml   # cron + workflow_dispatch
├ src/
│  ├ domain/        keyword.py, report.py, slug.py, content_policy.py, feed.py, retention.py
│  ├ ports/         keyword_source.py, report_generator.py, site_publisher.py
│  ├ application/   generate_daily_reports.py
│  ├ infrastructure/
│  │   github_issue_source.py, openai_generator.py, anthropic_generator.py,
│  │   fallback_generator.py, static_site_publisher.py, _ai_prompt.py, _http.py
│  ├ config.py      # 環境変数の読み取り
│  └ main.py        # 配線・エントリポイント
├ site/             # Pages 公開対象。蓄積のためリポジトリで追跡（reports/*.html + feed.xml + index.html）
├ requirements.txt  # 依存なし
└ docs/ddd-design.md
```

---

## 10. 初期リリースのスコープ

**含める**: 手動 Issue 登録 / Open Issue 取得 → OpenAI(主)・Anthropic(副)生成 / HTML+RSS 生成・Pages 公開 /
cron(1日1回)+手動実行 / PocketDigest へ手動ソース追加で閲覧検証。

**含めない（後続）**: memo-android-app の自動 Issue 登録 / PocketDigest 改修 / 画像・全文検索・認証。

---

## 11. フェーズ別実装計画

- **Phase 0 基盤**: リポジトリ・ディレクトリ雛形・Pages 有効化・Secrets 登録・workflow_dispatch 雛形。検証=空ワークフロー手動実行成功。
- **Phase 1 生成**: domain/ports + GitHubIssueKeywordSource + OpenAiReportGenerator + UseCase。検証=手動実行で Issue を読み 120 文字以上の `site/reports/<slug>.html` 出力。
- **Phase 2 配信**: StaticSitePublisher(HTML+feed.xml) + deploy-pages。検証=Pages URL の feed.xml/HTML がブラウザで開け互換構造。
- **Phase 3 冗長化+蓄積**: Anthropic フォールバック + 複数キーワード + 蓄積（site/ をコミット）+ 保持ポリシー（期間+件数, ReportRetentionPolicy）+ 直近 N 件フィード。検証=OpenAI 無効でも Anthropic 生成、複数 Issue 全件レポート化、古い/超過レポートが削除される。
- **Phase 4 定期化**: cron 有効化 + GenerationRun ログ。検証=スケジュール実行で日次自動公開。
- **Phase 5（別計画）**: PocketDigest 正式ソース化・二重 AI 回避 / memo-android-app の Issue 自動登録。

---

## 12. 検証（E2E）

1. キーワード Issue を 1〜2 件手動作成。
2. Actions `Generate Reports` を手動実行 → `site/reports/<date>-<slug>.html` と `feed.xml` が Pages 公開。
3. feed.xml・レポ HTML をブラウザで開き `<article>`+`<p>`・120 文字以上を確認。
4. PocketDigest のソース管理に feed.xml URL を追加 → プルリフレッシュ → 記事として取得・抽出・表示。
5. （Phase3 後）OpenAI キー無効化で Anthropic フォールバック確認。

---

## 13. 論点

- Pages 有効化が前提。RSS 方式はリポジトリ Public 推奨（キーワード/レポートが公開される）。非公開希望なら将来 API 直接読込方式へ。
- API コスト = 1日1回 × Open Issue 数。Actions 無料枠（Public は実質無制限）内。
- 二重 AI 処理（本バックエンド + PocketDigest 再 enrichment）は今フェーズ許容。回避は Phase5 で `categoryLocked`/スキップ対応。
- 日本語キーワードのスラッグは ASCII 化 + md5 で URL 安全化（`ReportSlugFactory`）。
- 蓄積はリポジトリへのコミットで実現。古いレポートを `git rm` しても Git 履歴には blob が残るため、**履歴サイズはゆっくり増え続ける**（個人・低頻度なら数年は無視可）。肥大化が問題化した場合は orphan ブランチ運用や履歴圧縮で対処。作業ツリーと公開サイト自体は保持ポリシーで一定に保たれる。
- 保持ポリシーは期間（既定30日）+ 件数（既定100件）の併用。`max_count ≧ max_feed_items` を強制してフィードのリンク切れを防ぐ。
