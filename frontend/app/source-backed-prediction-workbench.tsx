"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  canonicalTeamName,
  matchLabel,
  teamLabel,
} from "./team-labels";
import { localizeReportText } from "./report-text";

type Scoreline = {
  home_goals: number;
  away_goals: number;
  probability: number;
};

type PredictionPayload = {
  id: string;
  home_team: string;
  away_team: string;
  probabilities: {
    home_win: number;
    draw: number;
    away_win: number;
  };
  top_scorelines: Scoreline[];
  confidence_level: string;
};

type PredictionDatasetPayload = {
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

type SourceSummaryPayload = {
  ingested_source_count: number;
  snapshot_count: number;
  normalized_fact_count: number;
  validated_fact_count: number;
  conflict_count: number;
};

type AIReportPayload = {
  id: string;
  provider_name: string;
  model_name: string;
  content: string;
  input_summary: Record<string, unknown>;
};

type SourceBackedPredictionPayload = {
  prediction: PredictionPayload;
  dataset: PredictionDatasetPayload;
  source_summary: SourceSummaryPayload;
  ai_report?: AIReportPayload | null;
};

type TomorrowMatchPayload = {
  source_name: string;
  event_id: string;
  home_team: string;
  away_team: string;
  kickoff_at: string | null;
};

type TomorrowMatchesPayload = {
  target_date: string;
  match_count: number;
  matches: TomorrowMatchPayload[];
};

type SourceCategoryOption = {
  value: string;
  label: string;
};

const SOURCE_CATEGORY_OPTIONS: SourceCategoryOption[] = [
  { value: "", label: "全部已配置数据源" },
  { value: "ranking", label: "排名" },
  { value: "team_form", label: "球队状态" },
  { value: "injury", label: "伤停" },
  { value: "odds", label: "赔率" },
  { value: "news_sentiment", label: "新闻情绪" },
  { value: "player", label: "球员数据" },
  { value: "schedule", label: "赛程" },
];

const AI_REPORT_PROVIDER_OPTIONS = [
  { value: "gpt", label: "GPT" },
  { value: "deepseek", label: "DeepSeek" },
];

type Props = {
  backendReady: boolean;
};

export function SourceBackedPredictionWorkbench({ backendReady }: Props) {
  const [homeTeam, setHomeTeam] = useState(teamLabel("Brazil"));
  const [awayTeam, setAwayTeam] = useState(teamLabel("Croatia"));
  const [tomorrowMatches, setTomorrowMatches] = useState<TomorrowMatchPayload[]>(
    [],
  );
  const [tomorrowTargetDate, setTomorrowTargetDate] = useState<string | null>(null);
  const [selectedMatchKey, setSelectedMatchKey] = useState("manual");
  const [isLoadingMatches, setIsLoadingMatches] = useState(backendReady);
  const [matchError, setMatchError] = useState<string | null>(null);
  const [category, setCategory] = useState("");
  const [simulationCount, setSimulationCount] = useState(1000);
  const [generateAIReport, setGenerateAIReport] = useState(false);
  const [aiReportProvider, setAIReportProvider] = useState("gpt");
  const [prediction, setPrediction] =
    useState<SourceBackedPredictionPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  const selectedCategoryLabel = useMemo(
    () =>
      SOURCE_CATEGORY_OPTIONS.find((option) => option.value === category)?.label ??
      "自定义数据源集合",
    [category],
  );

  useEffect(() => {
    if (!backendReady) {
      return;
    }

    void loadTomorrowMatches();
  }, [backendReady]);

  async function loadTomorrowMatches() {
    setMatchError(null);
    setIsLoadingMatches(true);

    try {
      const response = await fetch("/api/sources/tomorrow-matches", {
        cache: "no-store",
      });
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `明日赛程加载失败，HTTP 状态码 ${response.status}`);
      }

      const payload = (await response.json()) as TomorrowMatchesPayload;
      setTomorrowMatches(payload.matches);
      setTomorrowTargetDate(payload.target_date);

      if (payload.matches.length) {
        selectTomorrowMatch("0", payload.matches);
      } else {
        setSelectedMatchKey("manual");
      }
    } catch (caughtError) {
      setMatchError(
        caughtError instanceof Error ? caughtError.message : "明日赛程加载失败。",
      );
      setTomorrowMatches([]);
      setTomorrowTargetDate(null);
      setSelectedMatchKey("manual");
    } finally {
      setIsLoadingMatches(false);
    }
  }

  function selectTomorrowMatch(
    key: string,
    matches: TomorrowMatchPayload[] = tomorrowMatches,
  ) {
    setSelectedMatchKey(key);
    if (key === "manual") {
      return;
    }

    const selectedIndex = Number(key);
    const match = matches[selectedIndex];
    if (!match) {
      return;
    }

    setHomeTeam(teamLabel(match.home_team));
    setAwayTeam(teamLabel(match.away_team));
  }

  async function runPrediction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsRunning(true);

    try {
      const trimmedHomeTeam = homeTeam.trim();
      const trimmedAwayTeam = awayTeam.trim();
      if (!trimmedHomeTeam || !trimmedAwayTeam) {
        throw new Error("主队和客队名称都必须填写。");
      }
      const canonicalHomeTeam = canonicalTeamName(trimmedHomeTeam);
      const canonicalAwayTeam = canonicalTeamName(trimmedAwayTeam);

      const response = await fetch("/api/predictions/from-sources", {
        method: "POST",
        headers: {
          "content-type": "application/json",
        },
        body: JSON.stringify({
          home_team: canonicalHomeTeam,
          away_team: canonicalAwayTeam,
          category: category || undefined,
          simulation_count: simulationCount,
          seed: 20260614,
          generate_ai_report: generateAIReport,
          ai_report_provider: generateAIReport ? aiReportProvider : undefined,
        }),
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `预测失败，HTTP 状态码 ${response.status}`);
      }

      setPrediction((await response.json()) as SourceBackedPredictionPayload);
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "基于数据源的预测失败。",
      );
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <section
      className="prediction-panel prediction-workbench"
      aria-label="基于数据源的比赛预测"
    >
      <div className="prediction-copy">
        <p className="eyebrow">实时数据源预测</p>
        <h2>
          {prediction
            ? matchLabel(
                prediction.prediction.home_team,
                prediction.prediction.away_team,
              )
            : "选择球队，然后抓取数据源"}
        </h2>
        <p className="summary compact">
          这个流程会验证已配置的数据源，用已验证事实构建预测数据集，
          然后运行蒙特卡洛预测引擎。DeepSeek/GPT 只用于报告和权重建议。
        </p>
      </div>

      <form className="prediction-form" onSubmit={runPrediction}>
        <div className="fixture-picker">
          <label>
            <span className="label">明日比赛</span>
            <select
              disabled={isLoadingMatches}
              value={selectedMatchKey}
              onChange={(event) => selectTomorrowMatch(event.target.value)}
            >
              <option value="manual">
                {isLoadingMatches
                  ? "正在抓取明日赛程..."
                  : tomorrowMatches.length
                    ? "手动输入球队"
                    : "未抓到明日比赛，可手动输入"}
              </option>
              {tomorrowMatches.map((match, index) => (
                <option key={matchKey(match, index)} value={String(index)}>
                  {fixtureOptionLabel(match)}
                </option>
              ))}
            </select>
          </label>
          <div className="fixture-picker-actions">
            <p className="fixture-picker-note">
              {tomorrowTargetDate
                ? `目标日期 ${tomorrowTargetDate}，已加载 ${tomorrowMatches.length} 场。`
                : isLoadingMatches
                  ? "正在从赛程数据源抓取第二天出战队伍。"
                  : "会从赛程数据源抓取第二天出战队伍。"}
            </p>
            <button
              className="secondary-button"
              disabled={!backendReady || isLoadingMatches}
              onClick={() => void loadTomorrowMatches()}
              type="button"
            >
              {isLoadingMatches ? "加载中" : "刷新赛程"}
            </button>
          </div>
          {matchError ? <p className="fixture-picker-error">{matchError}</p> : null}
        </div>
        <label>
          <span className="label">主队</span>
          <input
            value={homeTeam}
            onChange={(event) => {
              setSelectedMatchKey("manual");
              setHomeTeam(event.target.value);
            }}
            required
          />
        </label>
        <label>
          <span className="label">客队</span>
          <input
            value={awayTeam}
            onChange={(event) => {
              setSelectedMatchKey("manual");
              setAwayTeam(event.target.value);
            }}
            required
          />
        </label>
        <label className="full-width-field">
          <span className="label">数据源范围</span>
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          >
            {SOURCE_CATEGORY_OPTIONS.map((option) => (
              <option key={option.value || "all"} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="label">模拟次数</span>
          <input
            min={100}
            max={20000}
            step={100}
            type="number"
            value={simulationCount}
            onChange={(event) => setSimulationCount(Number(event.target.value))}
            required
          />
        </label>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={generateAIReport}
            onChange={(event) => setGenerateAIReport(event.target.checked)}
          />
          <span>预测后生成 GPT/DeepSeek 报告</span>
        </label>
        <fieldset className="ai-provider-field" disabled={!generateAIReport}>
          <legend className="label">AI 报告模型</legend>
          <div className="ai-provider-toggle">
            {AI_REPORT_PROVIDER_OPTIONS.map((option) => (
              <label
                className={
                  aiReportProvider === option.value
                    ? "ai-provider-option selected"
                    : "ai-provider-option"
                }
                key={option.value}
              >
                <input
                  checked={aiReportProvider === option.value}
                  name="ai-report-provider"
                  onChange={() => setAIReportProvider(option.value)}
                  type="radio"
                  value={option.value}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <button
          className="submit-button"
          disabled={!backendReady || isRunning}
          type="submit"
        >
          {isRunning ? "正在抓取并预测" : "运行数据源预测"}
        </button>
        <p className="summary compact prediction-scope">
          范围：{selectedCategoryLabel}。全量数据源会先采集快照再生成概率，
          因此耗时更长。
        </p>
      </form>

      {error ? <p className="source-ops-error">{error}</p> : null}

      {prediction ? (
        <>
          <div className="probability-grid">
            <div>
              <p className="label">主胜</p>
              <strong>
                {formatPercent(prediction.prediction.probabilities.home_win)}
              </strong>
            </div>
            <div>
              <p className="label">平局</p>
              <strong>{formatPercent(prediction.prediction.probabilities.draw)}</strong>
            </div>
            <div>
              <p className="label">客胜</p>
              <strong>
                {formatPercent(prediction.prediction.probabilities.away_win)}
              </strong>
            </div>
            <div>
              <p className="label">置信等级</p>
              <strong>{prediction.prediction.confidence_level}</strong>
            </div>
          </div>

          <div className="source-ops-summary prediction-source-summary">
            <article>
              <p className="label">数据源</p>
              <strong>{prediction.source_summary.ingested_source_count}</strong>
            </article>
            <article>
              <p className="label">快照</p>
              <strong>{prediction.source_summary.snapshot_count}</strong>
            </article>
            <article>
              <p className="label">事实</p>
              <strong>{prediction.source_summary.normalized_fact_count}</strong>
            </article>
            <article>
              <p className="label">已验证</p>
              <strong>{prediction.source_summary.validated_fact_count}</strong>
            </article>
          </div>

          <div className="dataset-grid">
            <article>
              <p className="label">{teamLabel(prediction.dataset.home_team)}</p>
              <strong>{prediction.dataset.home.attack_index.toFixed(3)}</strong>
              <span>进攻指数</span>
              <span>
                {prediction.dataset.home.defense_weakness.toFixed(3)} 防守弱点
              </span>
            </article>
            <article>
              <p className="label">{teamLabel(prediction.dataset.away_team)}</p>
              <strong>{prediction.dataset.away.attack_index.toFixed(3)}</strong>
              <span>进攻指数</span>
              <span>
                {prediction.dataset.away.defense_weakness.toFixed(3)} 防守弱点
              </span>
            </article>
            <article>
              <p className="label">冲突惩罚</p>
              <strong>{prediction.dataset.conflict_count}</strong>
              <span>影响置信等级</span>
            </article>
          </div>

          {prediction.ai_report ? (
            <div className="source-category">
              <div className="source-category-header">
                <p className="label">AI 报告</p>
                <span>
                  {prediction.ai_report.provider_name} /{" "}
                  {prediction.ai_report.model_name}
                </span>
              </div>
              <p className="summary compact">
                {localizeReportText(prediction.ai_report.content)}
              </p>
            </div>
          ) : null}

          <ol className="scorelines">
            {prediction.prediction.top_scorelines.map((scoreline) => (
              <li
                key={`${scoreline.home_goals}-${scoreline.away_goals}-${scoreline.probability}`}
              >
                <span>
                  {scoreline.home_goals}-{scoreline.away_goals}
                </span>
                <span>{formatPercent(scoreline.probability)}</span>
              </li>
            ))}
          </ol>

          <a
            className="evidence-link"
            href={`/predictions/${prediction.prediction.id}`}
          >
            查看预测证据详情
          </a>
        </>
      ) : (
        <p className="summary compact prediction-empty-state">
          可先选择“排名”进行快速冒烟测试，或选择“全部已配置数据源”运行完整抓取和验证流程。
        </p>
      )}
    </section>
  );
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function matchKey(match: TomorrowMatchPayload, index: number) {
  return `${index}-${match.home_team}-${match.away_team}-${match.kickoff_at ?? ""}`;
}

function fixtureOptionLabel(match: TomorrowMatchPayload) {
  return `${formatKickoff(match.kickoff_at)} · ${matchLabel(
    match.home_team,
    match.away_team,
  )}`;
}

function formatKickoff(value: string | null) {
  if (!value) {
    return "时间待定";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
