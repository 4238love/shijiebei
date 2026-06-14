"use client";

import { useMemo, useState } from "react";

type OperationAction = "ingest" | "validate";

type IngestionResult = {
  source_name: string;
  category: string | null;
  status: string;
  item_count: number;
  facts: { fact_type: string }[];
  matches: unknown[];
  message: string | null;
};

type ValidatedFact = {
  fact_type: string;
  entity_key: string;
  status: string;
  sources: string[];
};

type OperationResponse = {
  results: IngestionResult[];
  validated_facts?: ValidatedFact[];
};

type OperationSummary = {
  sourceCount: number;
  itemCount: number;
  factCount: number;
  matchCount: number;
  validatedCount: number;
  statuses: Record<string, number>;
};

type SourceOperationsProps = {
  categories: string[];
};

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

export function SourceOperations({ categories }: SourceOperationsProps) {
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [isRunning, setIsRunning] = useState(false);
  const [lastAction, setLastAction] = useState<OperationAction | null>(null);
  const [result, setResult] = useState<OperationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const summary = useMemo(() => summarizeOperation(result), [result]);

  async function runOperation(action: OperationAction) {
    setIsRunning(true);
    setLastAction(action);
    setError(null);

    try {
      const response = await fetch(`/api/sources/${action}`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
        },
        body: JSON.stringify(
          selectedCategory === "all" ? {} : { category: selectedCategory },
        ),
      });

      const payload = (await response.json()) as OperationResponse | { detail?: string };
      if (!response.ok) {
        throw new Error(
          "detail" in payload && payload.detail
            ? payload.detail
            : `数据源${actionLabel(action)}失败，HTTP ${response.status}`,
        );
      }

      setResult(payload as OperationResponse);
    } catch (operationError) {
      setResult(null);
      setError(
        operationError instanceof Error
          ? operationError.message
          : "数据源操作失败",
      );
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <section className="source-ops" aria-label="数据源操作">
      <div>
        <p className="eyebrow">操作控制台</p>
        <h2>触发基于快照的数据接入</h2>
        <p className="summary compact">
          可以对单个分类或完整目录运行后端数据源适配器。
          校验会交叉检查归一化事实，并汇总已确认/有冲突的覆盖情况。
        </p>
      </div>

      <div className="source-ops-controls">
        <label>
          <span className="label">分类</span>
          <select
            disabled={isRunning}
            onChange={(event) => setSelectedCategory(event.target.value)}
            value={selectedCategory}
          >
            <option value="all">全部首轮数据分类</option>
            {categories.map((category) => (
              <option key={category} value={category}>
                {categoryLabel(category)}
              </option>
            ))}
          </select>
        </label>

        <div className="source-ops-buttons">
          <button disabled={isRunning} onClick={() => runOperation("ingest")}>
            {isRunning && lastAction === "ingest" ? "抓取中..." : "执行抓取"}
          </button>
          <button disabled={isRunning} onClick={() => runOperation("validate")}>
            {isRunning && lastAction === "validate"
              ? "校验中..."
              : "执行校验"}
          </button>
        </div>
      </div>

      {summary ? (
        <div className="source-ops-summary" aria-live="polite">
          <article>
            <p className="label">数据源</p>
            <strong>{summary.sourceCount}</strong>
          </article>
          <article>
            <p className="label">条目</p>
            <strong>{summary.itemCount}</strong>
          </article>
          <article>
            <p className="label">事实</p>
            <strong>{summary.factCount}</strong>
          </article>
          <article>
            <p className="label">已验证</p>
            <strong>{summary.validatedCount}</strong>
          </article>
          <article className="wide-card">
            <p className="label">运行状态</p>
            <div className="source-status-row">
              {Object.entries(summary.statuses).map(([status, count]) => (
                <span key={status}>
                  {statusLabel(status)}：{count}
                </span>
              ))}
            </div>
          </article>
        </div>
      ) : null}

      {error ? (
        <p className="source-ops-error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}

function actionLabel(action: OperationAction) {
  return action === "ingest" ? "抓取" : "校验";
}

function categoryLabel(category: string) {
  return CATEGORY_LABELS[category] ?? category.replaceAll("_", " ");
}

function statusLabel(status: string) {
  return STATUS_LABELS[status] ?? status;
}

function summarizeOperation(result: OperationResponse | null): OperationSummary | null {
  if (!result) {
    return null;
  }

  return result.results.reduce<OperationSummary>(
    (summary, source) => {
      summary.sourceCount += 1;
      summary.itemCount += source.item_count;
      summary.factCount += source.facts.length;
      summary.matchCount += source.matches.length;
      summary.validatedCount = result.validated_facts?.length ?? 0;
      summary.statuses[source.status] = (summary.statuses[source.status] ?? 0) + 1;
      return summary;
    },
    {
      sourceCount: 0,
      itemCount: 0,
      factCount: 0,
      matchCount: 0,
      validatedCount: 0,
      statuses: {},
    },
  );
}
