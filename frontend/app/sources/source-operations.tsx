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
            : `Source ${action} failed with ${response.status}`,
        );
      }

      setResult(payload as OperationResponse);
    } catch (operationError) {
      setResult(null);
      setError(
        operationError instanceof Error
          ? operationError.message
          : "Source operation failed",
      );
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <section className="source-ops" aria-label="Source operations">
      <div>
        <p className="eyebrow">Operations console</p>
        <h2>Trigger snapshot-backed intake</h2>
        <p className="summary compact">
          Run a selected category or the full catalog through the backend source
          adapters. Validate also cross-checks normalized facts and reports
          confirmed/conflicting coverage.
        </p>
      </div>

      <div className="source-ops-controls">
        <label>
          <span className="label">Category</span>
          <select
            disabled={isRunning}
            onChange={(event) => setSelectedCategory(event.target.value)}
            value={selectedCategory}
          >
            <option value="all">All first-wave categories</option>
            {categories.map((category) => (
              <option key={category} value={category}>
                {category.replace("_", " ")}
              </option>
            ))}
          </select>
        </label>

        <div className="source-ops-buttons">
          <button disabled={isRunning} onClick={() => runOperation("ingest")}>
            {isRunning && lastAction === "ingest" ? "Ingesting..." : "Run ingest"}
          </button>
          <button disabled={isRunning} onClick={() => runOperation("validate")}>
            {isRunning && lastAction === "validate"
              ? "Validating..."
              : "Run validate"}
          </button>
        </div>
      </div>

      {summary ? (
        <div className="source-ops-summary" aria-live="polite">
          <article>
            <p className="label">Sources</p>
            <strong>{summary.sourceCount}</strong>
          </article>
          <article>
            <p className="label">Items</p>
            <strong>{summary.itemCount}</strong>
          </article>
          <article>
            <p className="label">Facts</p>
            <strong>{summary.factCount}</strong>
          </article>
          <article>
            <p className="label">Validated</p>
            <strong>{summary.validatedCount}</strong>
          </article>
          <article className="wide-card">
            <p className="label">Run status</p>
            <div className="source-status-row">
              {Object.entries(summary.statuses).map(([status, count]) => (
                <span key={status}>
                  {status}: {count}
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
