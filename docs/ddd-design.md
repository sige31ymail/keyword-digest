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
| キーワード登録 | Issue を作成すること（今フェーズは手動）。Open=生成対象、Close=完了/停止。 |
| 一度だけ生成 | 同一キーワードの記事が既にあれば再生成せず、生成成功した Issue を自動クローズする運用。記事は恒久保存され、純粋な記事ライブラリを成す。 |
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
| ReportRetentionPolicy | 期間（max_age_days）+ 件数（max_count）の併用で保持/削除を判定。古いか件数超過のいずれかで削除。PocketDigest の `PruneOfflineLibraryUseCase`（期限/件数ベース整理）と対称。保持件数 ≧ フィード掲載件数を保証しリンク切れを防ぐ。**既定では無効（`RETENTION_ENABLED=false`）で恒久保存**、有効化時のみ適用。 |

---

## 5. ポート

| ポート | 役割 | 実装（Phase） |
| --- | --- | --- |
| `KeywordSource` | Open Issue 一覧 → `list[Keyword]` | GitHubIssueKeywordSource（P1） |
| `ReportGenerator` | `Keyword → Report` 生成 | DeepSeekPipeline（主・P6）/ Anthropic（副・P3）/ OpenAi（後方互換・P1）/ Fallback（P3） |
| `WebSearch` | `query → SearchFinding`（事実＋出典） | TavilyWebSearch（既定・P6）/ OpenAiWebSearch（予備・P6） |
| `IssueCloser` | 生成済み Issue をクローズ（一度だけ生成モデル） | GitHubIssueKeywordSource（P7。同クラスが兼務） |
| `SitePublisher` | HTML + feed.xml の書き出し・既存走査・削除 | StaticSitePublisher（P2）。公開は Actions の deploy-pages |

**生成パイプライン（DeepSeekPipelineReportGenerator）**: 単段生成では品質が頭打ちのため、
キーワード1件を以下の5段階で処理する。重い推論（選別・構成・執筆・検証）は DeepSeek
（`deepseek-v4-pro`, OpenAI 互換 `api.deepseek.com`）が担い、DeepSeek に欠けている Web 検索だけ
`WebSearch` ポートへ委譲する。

1. **クエリ生成** … DeepSeek がキーワードから検索クエリを `MAX_SEARCH_QUERIES`(=3) 件生成。
2. **検索＋選別・要約** … 各クエリを `WebSearch` で実行し事実＋出典を回収、DeepSeek が選別・要約。
3. **論点整理・記事構成** … DeepSeek がタイトルとアウトラインを生成。
4. **本文生成** … DeepSeek が構成と事実から段落本文を執筆。
5. **ファクトチェック** … DeepSeek が本文を事実と照合し、裏付けの無い主張を削除・修正。

出典は検索段で集めた `url_citation`／Tavily 結果 URL を機械的に回収し、本文末尾へ付与する。
段の失敗は `GenerationError` として送出し、Fallback が副（Anthropic 単段）へ切り替える。

---

## 6. アプリケーションサービス

### GenerateDailyReportsUseCase（中核）
```
1. keywords = KeywordSource.list_open()
2. existing = SitePublisher.list_existing_items()      # 蓄積済み(checkoutで取得)
   done = {item.keyword for item in existing}           # 生成済みキーワード集合
3. for each keyword:
     if keyword in done:                                # 冪等: 一度だけ生成
       skip ; IssueCloser.close(keyword)（auto_close時） ; continue
     try:
       report = ReportGenerator.generate(keyword)       # 主DeepSeek多段、失敗時Anthropic
       ReportContentPolicy.validate(report.body)
       SitePublisher.write_report_page(report)           # reports/<slug>.html
       IssueCloser.close(keyword)（auto_close時）         # 成功した Issue をクローズ
     except: 記録して次へ（1件の失敗を全体に波及させない）
4. items = SitePublisher.list_existing_items()          # 今回生成分を含む全件
   if retention_enabled:                                # 既定 false（恒久保存）
     keep, remove = ReportRetentionPolicy.partition(items, now, max_age_days, max_count)
     SitePublisher.delete_reports(remove)
   else:
     keep = items                                       # 削除せず全件保持
5. feed = FeedAssembler.assemble(keep, max_feed_items)  # 保持分から直近 N 件
   SitePublisher.write_feed(feed)                       # feed.xml + index.html
6. （Actions が site/ をコミット&push して蓄積 → Pages へデプロイ）
7. GenerationRun を集計してログ出力（成功/スキップ/失敗/クローズ/削除）
```

**永続化モデル（一度だけ生成して恒久保存）**: Issue はワンショットの生成依頼として扱う。
既に同一キーワードの記事があれば**再生成をスキップ**（`kd:keyword` メタで判定）し、生成に成功した
Issue は **`IssueCloser` で自動クローズ**して再生成対象（Open）から外す。記事は削除しない
（`RETENTION_ENABLED=false`）ため、各レポートは URL で恒久的に残る純粋な記事ライブラリになる。
RSS は `FeedAssembler` が直近 N 件（`max_feed_items`=20）に絞るのでフィード自体は肥大化しない。

**蓄積（git 永続化）**: `site/` はリポジトリで追跡し、ワークフローが毎回 `git add site && commit && push`
する。`checkout` で過去レポートを取り戻す。保持ポリシーを有効化（`RETENTION_ENABLED=true`）する場合は
フィード窓（20）＜ 保持窓（`max_count`=100, `max_age_days`=30）としてリンク切れを防ぐ。

---

## 7. インフラ層

PocketDigest の軽量方針（重い依存を避ける）を踏襲し、**Python 標準ライブラリのみ**で実装
（urllib / json / xml / hashlib）。外部 SDK・テンプレートエンジンは不使用。

| 実装 | 技術 |
| --- | --- |
| GitHubIssueKeywordSource | REST `GET /repos/{owner}/{repo}/issues?state=open`（PR を除外）。`IssueCloser` も兼務し、成功時に `PATCH .../issues/{n}`（state=closed）＋任意でコメント投稿 |
| DeepSeekPipelineReportGenerator | **主**。`api.deepseek.com`（OpenAI 互換 `/chat/completions`）を chat で呼び、5段階で生成。検索は `WebSearch` ポートへ委譲。各段は `response_format=json_object` で構造化出力 |
| TavilyWebSearch | **既定の検索バックエンド**。`POST https://api.tavily.com/search`（`include_answer`）で本文抽出済みの結果＋要約＋出典を取得 |
| OpenAiWebSearch | 予備の検索バックエンド。Responses API（`/v1/responses`）の `web_search` ツールで事実＋`url_citation` を取得 |
| OpenAiReportGenerator | 後方互換の単段生成。DeepSeek 未設定時に使用。`web_search` ツール or Chat Completions（`OPENAI_WEB_SEARCH=false`） |
| AnthropicReportGenerator | **副（フォールバック）**。Anthropic Messages（`claude-haiku-4-5`）。検索なし単段 |
| FallbackReportGenerator | 主失敗時に副へ切替（PocketDigest `FallbackAiEnrichmentClient` と同思想） |
| StaticSitePublisher | 文字列テンプレで HTML、手組みで RSS 2.0。`<meta name="kd:*">` でメタ情報を埋め、再実行時に既存レポートを復元。`delete_reports` で保持ポリシー削除を実行 |

Secrets（Actions）: `DEEPSEEK_API_KEY`（主生成）/ `TAVILY_API_KEY`（既定検索）/ `OPENAI_API_KEY`（予備検索・後方互換）/ `ANTHROPIC_API_KEY`（副生成）/ `GITHUB_TOKEN`（自動）。
環境変数: `MAX_FEED_ITEMS`(20)。永続化: `RETENTION_ENABLED`(false=恒久保存) / `AUTO_CLOSE_ISSUES`(true)。保持ポリシー有効時のみ `RETENTION_MAX_AGE_DAYS`(30) / `RETENTION_MAX_COUNT`(100) を参照。
ワークフロー権限は蓄積コミットのため `contents: write`、Issue 自動クローズのため `issues: write`。
生成: `DEEPSEEK_MODEL`(deepseek-v4-pro) / `DEEPSEEK_BASE_URL`(api.deepseek.com) / `MAX_SEARCH_QUERIES`(3)。
検索: `TAVILY_MAX_RESULTS`(5)。OpenAI 予備時は `OPENAI_WEB_SEARCH`(true) / `OPENAI_MODEL` / `OPENAI_SEARCH_CONTEXT_SIZE`(medium)。
コスト注記: 1レポートあたり DeepSeek chat 5回 + 検索 3回（Tavily）。DeepSeek には検索機能が無いため
外部検索 API が必須。Anthropic フォールバックは検索なし。

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
│  ├ ports/         keyword_source.py, report_generator.py, web_search.py,
│  │                issue_closer.py, site_publisher.py
│  ├ application/   generate_daily_reports.py
│  ├ infrastructure/
│  │   github_issue_source.py, deepseek_generator.py, openai_generator.py,
│  │   anthropic_generator.py, fallback_generator.py, static_site_publisher.py,
│  │   tavily_web_search.py, openai_web_search.py,
│  │   _ai_prompt.py, _pipeline_prompts.py, _http.py
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
- **Phase 6 品質強化**: 単段生成から **DeepSeek 多段パイプライン**（クエリ生成→検索→選別要約→構成→本文→ファクトチェック）へ刷新。検索を `WebSearch` ポート（Tavily 既定 / OpenAI 予備）へ分離。記者ペルソナで多角的・長文（1800〜3000字）化。検証=同一キーワードで旧単段より事実密度・出典の妥当性・読み応えが向上、出典付きで公開される。
- **Phase 7 永続化（一度だけ生成）**: `IssueCloser` ポート追加。冪等な再生成スキップ（`kd:keyword` 判定）＋恒久保存（`RETENTION_ENABLED=false`）＋成功 Issue の自動クローズ（`issues: write`）。検証=既存キーワードはスキップされ新規のみ生成、記事は削除されず、成功 Issue が Open から外れる。

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
- 蓄積はリポジトリへのコミットで実現。**既定は恒久保存（`RETENTION_ENABLED=false`）で記事を削除しない**ため、作業ツリーと公開サイトに全レポートが残り、各記事は URL で永続アクセス可能。git 履歴も追記され続けるので **履歴サイズはゆっくり増え続ける**（個人・低頻度なら数年は無視可）。肥大化が問題化した場合は orphan ブランチ運用や履歴圧縮、あるいは保持ポリシー有効化で対処。
- 永続化モデルは「一度だけ生成して恒久保存」。同一キーワードは `kd:keyword` メタで判定して再生成をスキップし、成功した Issue は `IssueCloser` で自動クローズ（`AUTO_CLOSE_ISSUES=true`、`issues: write` 権限が必要）。再生成したい場合は対象記事 HTML を削除して Issue を Open し直す。**Issue は API では削除しづらい（REST 非対応 / GraphQL `deleteIssue` + 管理者権限）ためクローズで運用**し、依頼内容（note）も保全する。
- 保持ポリシー（任意）は期間（既定30日）+ 件数（既定100件）の併用。`max_count ≧ max_feed_items` を強制してフィードのリンク切れを防ぐ。有効化時のみ適用。
