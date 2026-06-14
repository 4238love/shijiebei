import { SourceOperations } from "./source-operations";

type SourceItem = {
  category: string;
  name: string;
  url: string;
  priority: number;
  adapter: string;
  notes: string;
};

type SourcesPayload = {
  missing_first_wave_categories: string[];
  sources: SourceItem[];
};

type SourceSnapshotMetadata = {
  id: string;
  source_name: string;
  category: string | null;
  status: string;
  path: string;
  content_hash: string;
  item_count: number;
  fact_count: number;
  match_count: number;
  message: string | null;
};

type SourceSnapshotsPayload = {
  snapshots: SourceSnapshotMetadata[];
};

const implementedAdapters = new Set([
  "betexplorer_odds",
  "espn_scoreboard",
  "espn_team_rosters",
  "espn_team_schedules",
  "fifa_ranking",
  "fifa_teams",
  "injury_news",
  "news_sentiment",
  "oddschecker_odds",
  "oddsportal_odds",
  "schema_org_schedule",
  "sportsmole_injuries",
  "transfermarkt_injuries",
  "transfermarkt_squads",
  "world_football_elo",
]);

const CATEGORY_LABELS: Record<string, string> = {
  injury: "伤停",
  news_sentiment: "新闻情绪",
  odds: "赔率",
  player: "球员数据",
  ranking: "排名",
  schedule: "赛程",
  team_form: "球队状态",
};

const STATUS_LABELS: Record<string, string> = {
  failed: "失败",
  ingested: "已抓取",
  unsupported: "未支持",
};

async function fetchSources(): Promise<SourcesPayload | null> {
  const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

  try {
    const response = await fetch(`${backendUrl}/sources`, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return response.json();
  } catch {
    return null;
  }
}

async function fetchSnapshots(): Promise<SourceSnapshotsPayload | null> {
  const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

  try {
    const response = await fetch(`${backendUrl}/sources/snapshots`, {
      cache: "no-store",
    });
    if (!response.ok) {
      return null;
    }
    return response.json();
  } catch {
    return null;
  }
}

function groupByCategory(sources: SourceItem[]) {
  return sources.reduce<Record<string, SourceItem[]>>((groups, source) => {
    groups[source.category] = groups[source.category] ?? [];
    groups[source.category].push(source);
    return groups;
  }, {});
}

function adapterLabel(adapter: string) {
  return implementedAdapters.has(adapter) ? "实时解析器" : "已配置";
}

export default async function SourcesPage() {
  const [payload, snapshotPayload] = await Promise.all([
    fetchSources(),
    fetchSnapshots(),
  ]);
  const groups = payload ? groupByCategory(payload.sources) : {};
  const recentSnapshots = snapshotPayload?.snapshots.slice(0, 6) ?? [];

  return (
    <main className="shell">
      <section className="hero source-hero">
        <p className="eyebrow">数据源目录</p>
        <h1>实时数据接入地图</h1>
        <p className="summary">
          首轮爬取覆盖赛程、状态、排名、伤停、赔率、新闻情绪和球员数据。
          专用适配器会先生成快照，预测按钮不会在点击时直接抓取网页。
        </p>
      </section>

      {payload ? (
        <>
          <SourceOperations categories={Object.keys(groups).sort()} />

          <section className="source-health" aria-label="数据源覆盖">
            <article>
              <p className="label">已配置数据源</p>
              <strong>{payload.sources.length}</strong>
            </article>
            <article>
              <p className="label">缺失分类</p>
              <strong>{payload.missing_first_wave_categories.length}</strong>
            </article>
            <article>
              <p className="label">实时解析器</p>
              <strong>
                {
                  payload.sources.filter((source) =>
                    implementedAdapters.has(source.adapter),
                  ).length
                }
              </strong>
            </article>
          </section>

          {recentSnapshots.length ? (
            <section className="source-category" aria-label="最近快照">
              <div className="source-category-header">
                <p className="label">最近快照</p>
                <span>{recentSnapshots.length} 条记录</span>
              </div>
              <div className="source-list">
                {recentSnapshots.map((snapshot) => (
                  <article className="source-card" key={snapshot.id}>
                    <span className="source-pill source-pill-live">
                      {statusLabel(snapshot.status)}
                    </span>
                    <h2>{snapshot.source_name}</h2>
                    <p>
                      {categoryLabel(snapshot.category)} / 事实 {snapshot.fact_count} / 比赛{" "}
                      {snapshot.match_count}
                    </p>
                    <p>{snapshot.path}</p>
                  </article>
                ))}
              </div>
            </section>
          ) : null}

          <section className="source-grid">
            {Object.entries(groups).map(([category, sources]) => (
              <article key={category} className="source-category">
                <div className="source-category-header">
                  <p className="label">{categoryLabel(category)}</p>
                  <span>{sources.length} 个数据源</span>
                </div>
                <div className="source-list">
                  {sources
                    .sort((left, right) => left.priority - right.priority)
                    .map((source) => (
                      <a
                        className="source-card"
                        href={source.url}
                        key={source.name}
                        rel="noreferrer"
                        target="_blank"
                      >
                        <span
                          className={
                            implementedAdapters.has(source.adapter)
                              ? "source-pill source-pill-live"
                              : "source-pill"
                          }
                        >
                          {adapterLabel(source.adapter)}
                        </span>
                        <h2>{source.name}</h2>
                        <p>
                          优先级 {source.priority} / 适配器 {source.adapter}
                        </p>
                        <p>目标地址：{source.url}</p>
                      </a>
                    ))}
                </div>
              </article>
            ))}
          </section>
        </>
      ) : (
        <section className="prediction-panel">
          <h2>数据源 API 不可用</h2>
          <p className="summary compact">
            启动后端服务后才能查看实时数据源配置。
          </p>
        </section>
      )}
    </main>
  );
}

function categoryLabel(category: string | null) {
  if (!category) {
    return "未分类";
  }
  return CATEGORY_LABELS[category] ?? category.replaceAll("_", " ");
}

function statusLabel(status: string) {
  return STATUS_LABELS[status] ?? status;
}
