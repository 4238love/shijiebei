import {
  matchLabel,
  teamLabel,
} from "../../team-labels";
import { localizeReportText } from "../../report-text";
import { sourceNameLabel } from "../../source-labels";

type Scoreline = {
  home_goals: number;
  away_goals: number;
  probability: number;
};

type Prediction = {
  id: string;
  home_team: string;
  away_team: string;
  weight_version: string;
  simulation_count: number;
  expected_goals: Record<string, number>;
  probabilities: {
    home_win: number;
    draw: number;
    away_win: number;
  };
  top_scorelines: Scoreline[];
  confidence_level: string;
};

type PredictionDataset = {
  home_team: string;
  away_team: string;
  home: {
    attack_index: number;
    defense_weakness: number;
  };
  away: {
    attack_index: number;
    defense_weakness: number;
  };
  home_advantage: number;
  conflict_count: number;
};

type SourceSummary = {
  ingested_source_count: number;
  snapshot_count: number;
  normalized_fact_count: number;
  validated_fact_count: number;
  conflict_count: number;
};

type SourceEvidence = {
  source_name: string;
  category: string | null;
  status: string;
  snapshot_path: string | null;
  content_hash: string | null;
  item_count: number;
  fact_count: number;
  match_count: number;
  message: string | null;
};

type ValidatedFact = {
  fact_type: string;
  entity_key: string;
  status: string;
  value: unknown;
  sources: string[];
  conflicting_values: Record<string, string[]>;
};

type AIReport = {
  id: string;
  provider_name: string;
  model_name: string;
  content: string;
  input_summary: Record<string, unknown>;
};

type PredictionRecord = {
  prediction: Prediction;
  dataset: PredictionDataset | null;
  source_summary: SourceSummary | null;
  source_evidence: SourceEvidence[];
  validated_facts: ValidatedFact[];
  ai_report: AIReport | null;
};

type PageProps = {
  params: Promise<{ id: string }>;
};

async function fetchPredictionRecord(id: string): Promise<PredictionRecord | null> {
  const backendUrl = process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000";

  try {
    const response = await fetch(`${backendUrl}/predictions/${id}/record`, {
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

function percent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

const CATEGORY_LABELS: Record<string, string> = {
  injury: "伤停",
  news_sentiment: "新闻情绪",
  odds: "赔率",
  player: "球员数据",
  ranking: "排名",
  schedule: "赛程",
  team_form: "球队状态",
};

const FACT_TYPE_LABELS: Record<string, string> = {
  decimal_odds: "十进制赔率",
  injury_availability: "伤停可用性",
  injury_feed_signal: "伤停新闻信号",
  match_result: "比赛结果",
  news_sentiment: "新闻情绪",
  player_presence: "球员名单",
  team_elo_rating: "球队 Elo 评分",
  team_listed_player_count: "球队名单人数",
  team_news_sentiment: "球队新闻情绪",
  team_ranking_position: "球队排名",
  team_unavailable_player_count: "球队不可用球员数",
};

const STATUS_LABELS: Record<string, string> = {
  available: "可出场",
  confirmed: "已确认",
  conflicting: "有冲突",
  doubtful: "出战成疑",
  failed: "失败",
  ingested: "已抓取",
  injured: "受伤",
  missing: "缺失",
  out: "缺阵",
  stale: "过期",
  suspended: "停赛",
  unavailable: "不可用",
  unsupported: "未支持",
};

export default async function PredictionDetailPage({ params }: PageProps) {
  const { id } = await params;
  const record = await fetchPredictionRecord(id);

  if (!record) {
    return (
      <main className="shell">
        <section className="prediction-panel">
          <h1>未找到预测记录</h1>
          <p className="summary compact">
            后端仓库中没有这条预测记录，可能尚未生成或已被清理。
          </p>
        </section>
      </main>
    );
  }

  const { prediction, dataset, source_summary: sourceSummary } = record;
  const validatedFacts = record.validated_facts ?? [];

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">预测证据详情</p>
        <h1>{matchLabel(prediction.home_team, prediction.away_team)}</h1>
        <p className="summary">
          预测 ID <code>{prediction.id}</code>。权重版本{" "}
          <code>{prediction.weight_version}</code>。本页将概率输出、数据源驱动的
          预测数据集，以及用于构建它的快照证据拆开展示，便于复核。
        </p>
      </section>

      <section className="prediction-panel prediction-detail-panel">
        <div>
          <p className="eyebrow">蒙特卡洛输出</p>
          <h2>置信等级 {prediction.confidence_level}</h2>
          <p className="summary compact">
            {prediction.simulation_count.toLocaleString()} 次模拟。预期进球：{" "}
            {prediction.expected_goals.home.toFixed(2)} -{" "}
            {prediction.expected_goals.away.toFixed(2)}.
          </p>
        </div>
        <div className="probability-grid">
          <div>
            <p className="label">主胜</p>
            <strong>{percent(prediction.probabilities.home_win)}</strong>
          </div>
          <div>
            <p className="label">平局</p>
            <strong>{percent(prediction.probabilities.draw)}</strong>
          </div>
          <div>
            <p className="label">客胜</p>
            <strong>{percent(prediction.probabilities.away_win)}</strong>
          </div>
          <div>
            <p className="label">高概率比分</p>
            <strong>{prediction.top_scorelines.length}</strong>
          </div>
        </div>
        <ol className="scorelines">
          {prediction.top_scorelines.map((scoreline) => (
            <li
              key={`${scoreline.home_goals}-${scoreline.away_goals}-${scoreline.probability}`}
            >
              <span>
                {scoreline.home_goals}-{scoreline.away_goals}
              </span>
              <span>{percent(scoreline.probability)}</span>
            </li>
          ))}
        </ol>
      </section>

      {sourceSummary ? (
        <section className="source-ops-summary detail-summary">
          <article>
            <p className="label">数据源</p>
            <strong>{sourceSummary.ingested_source_count}</strong>
          </article>
          <article>
            <p className="label">快照</p>
            <strong>{sourceSummary.snapshot_count}</strong>
          </article>
          <article>
            <p className="label">事实</p>
            <strong>{sourceSummary.normalized_fact_count}</strong>
          </article>
          <article>
            <p className="label">已验证</p>
            <strong>{sourceSummary.validated_fact_count}</strong>
          </article>
        </section>
      ) : null}

      {dataset ? (
        <section className="dataset-grid detail-dataset">
          <article>
            <p className="label">{teamLabel(dataset.home_team)}</p>
            <strong>{dataset.home.attack_index.toFixed(3)}</strong>
            <span>进攻指数</span>
            <span>{dataset.home.defense_weakness.toFixed(3)} 防守弱点</span>
          </article>
          <article>
            <p className="label">{teamLabel(dataset.away_team)}</p>
            <strong>{dataset.away.attack_index.toFixed(3)}</strong>
            <span>进攻指数</span>
            <span>{dataset.away.defense_weakness.toFixed(3)} 防守弱点</span>
          </article>
          <article>
            <p className="label">主场优势</p>
            <strong>{dataset.home_advantage.toFixed(3)}</strong>
            <span>{dataset.conflict_count} 个冲突惩罚</span>
          </article>
        </section>
      ) : null}

      {record.ai_report ? (
        <section className="source-category">
          <div className="source-category-header">
            <p className="label">AI 报告</p>
            <span>
              {record.ai_report.provider_name} / {record.ai_report.model_name}
            </span>
          </div>
          <p className="summary compact">
            {localizeReportText(record.ai_report.content)}
          </p>
          <p className="summary compact">
            报告 ID <code>{record.ai_report.id}</code>。该报告仅用于复核说明，
            不会改写预测引擎的概率输出。
          </p>
        </section>
      ) : null}

      <section className="source-category">
        <div className="source-category-header">
          <p className="label">已验证事实</p>
          <span>{validatedFacts.length} 条记录</span>
        </div>
        {validatedFacts.length ? (
          <div className="evidence-grid">
            {validatedFacts.slice(0, 24).map((fact) => (
              <article
                className="evidence-card"
                key={`${fact.fact_type}-${fact.entity_key}-${formatFactValue(fact.value)}`}
              >
                <span className="source-pill source-pill-live">
                  {statusLabel(fact.status)}
                </span>
                <h2>{fact.entity_key}</h2>
                <p>{factTypeLabel(fact.fact_type)}</p>
                <p>取值：{formatFactValue(fact.value)}</p>
                <p>来源：{fact.sources.join(", ") || "无"}</p>
                {Object.keys(fact.conflicting_values).length ? (
                  <code>{JSON.stringify(fact.conflicting_values)}</code>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <p className="summary compact">
            这条记录没有持久化的已验证事实。
          </p>
        )}
      </section>

      <section className="source-category">
        <div className="source-category-header">
          <p className="label">数据源证据</p>
          <span>{record.source_evidence.length} 条记录</span>
        </div>
        {record.source_evidence.length ? (
          <div className="evidence-grid">
            {record.source_evidence.map((evidence) => (
              <article className="evidence-card" key={evidence.source_name}>
                <span className="source-pill source-pill-live">
                  {statusLabel(evidence.status)}
                </span>
                <h2>{sourceNameLabel(evidence.source_name)}</h2>
                <p>
                  {categoryLabel(evidence.category)} / 事实 {evidence.fact_count} / 比赛{" "}
                  {evidence.match_count}
                </p>
                {evidence.snapshot_path ? <p>{evidence.snapshot_path}</p> : null}
                {evidence.content_hash ? (
                  <code>{evidence.content_hash.slice(0, 16)}</code>
                ) : null}
                {evidence.message ? <p>{evidence.message}</p> : null}
              </article>
            ))}
          </div>
        ) : (
          <p className="summary compact">
            这条记录没有持久化的数据源快照证据。
          </p>
        )}
      </section>
    </main>
  );
}

function formatFactValue(value: unknown) {
  if (value === null || value === undefined) {
    return "无";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return statusLabel(String(value));
}

function categoryLabel(category: string | null) {
  if (!category) {
    return "未分类";
  }
  return CATEGORY_LABELS[category] ?? category.replaceAll("_", " ");
}

function factTypeLabel(factType: string) {
  return FACT_TYPE_LABELS[factType] ?? factType.replaceAll("_", " ");
}

function statusLabel(status: string) {
  return STATUS_LABELS[status] ?? status;
}
