import { localizeTeamNamesInText } from "./team-labels";

const REPORT_REPLACEMENTS: Array<[RegExp, string]> = [
  [/Here is the concise football prediction analysis for/gi, "以下是本场足球预测分析："],
  [/Match Analysis/gi, "比赛分析"],
  [/Statistical Summary/gi, "统计摘要"],
  [/Home Team/gi, "主队"],
  [/Away Team/gi, "客队"],
  [/Win Probability/gi, "取胜概率"],
  [/Expected Goals \(xG\)/gi, "预期进球"],
  [/Draw/gi, "平局"],
  [/Confidence Level/gi, "置信等级"],
  [/Low Confidence/gi, "低置信度"],
  [/Key Source Evidence/gi, "关键数据源证据"],
  [/Elo Ratings/gi, "Elo 评分"],
  [/Recent Form/gi, "近期状态"],
  [/Injuries/gi, "伤停"],
  [/Odds/gi, "赔率"],
  [/Conflict & Context/gi, "冲突与背景"],
  [/Market vs Model/gi, "市场与模型"],
  [/Fixture Timing/gi, "赛程时间"],
  [/source evidence/gi, "数据源证据"],
  [/statistical model/gi, "统计模型"],
  [/betting odds/gi, "博彩赔率"],
  [/win probability/gi, "取胜概率"],
  [/expected goals/gi, "预期进球"],
  [/unavailable player(s)?/gi, "不可用球员"],
  [/provided sources/gi, "已提供数据源"],
];

export function localizeReportText(content: string) {
  const withoutMarkdownMarkers = content
    .replaceAll("###", "")
    .replaceAll("**", "")
    .replace(/\s+-\s+/g, "；");

  return REPORT_REPLACEMENTS.reduce(
    (localizedText, [pattern, replacement]) =>
      localizedText.replace(pattern, replacement),
    localizeTeamNamesInText(withoutMarkdownMarkers),
  );
}
