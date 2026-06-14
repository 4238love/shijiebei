const SOURCE_LABELS: Record<string, string> = {
  "bbc-world-cup-football": "BBC 世界杯足球新闻",
  "bbc-world-cup-football-injuries": "BBC 世界杯伤停新闻",
  "betexplorer-world-cup": "BetExplorer 世界杯赔率",
  "espn-world-cup-rosters": "ESPN 世界杯球员名单",
  "espn-world-cup-scoreboard": "ESPN 世界杯赛程与比分",
  "espn-world-cup-scoreboard-form": "ESPN 世界杯近期状态",
  "espn-world-cup-team-schedules": "ESPN 世界杯球队赛程",
  "fifa-2026-fixtures": "FIFA 2026 世界杯赛程",
  "fifa-men-ranking": "FIFA 男足排名",
  "fifa-world-cup-news": "FIFA 世界杯新闻",
  "fifa-world-cup-news-injuries": "FIFA 世界杯伤停新闻",
  "fifa-world-cup-teams": "FIFA 世界杯球队名单",
  "oddschecker-world-cup": "OddsChecker 世界杯赔率",
  "oddsportal-world-cup": "OddsPortal 世界杯赔率",
  "oddsportal-world-cup-schedule": "OddsPortal 世界杯赛程",
  "sportsmole-world-cup-injuries": "Sports Mole 世界杯伤停",
  "transfermarkt-world-cup-2026-injuries": "Transfermarkt 世界杯伤停",
  "transfermarkt-world-cup-2026-squads": "Transfermarkt 世界杯阵容",
  "world-football-elo": "World Football Elo 评分",
  "world-football-elo-ranking": "World Football Elo 排名",
};

const ADAPTER_LABELS: Record<string, string> = {
  betexplorer_odds: "BetExplorer 赔率解析器",
  espn_scoreboard: "ESPN 赛程比分解析器",
  espn_team_rosters: "ESPN 球员名单解析器",
  espn_team_schedules: "ESPN 球队赛程解析器",
  fifa_ranking: "FIFA 排名解析器",
  fifa_teams: "FIFA 球队解析器",
  injury_news: "伤停新闻解析器",
  news_sentiment: "新闻情绪解析器",
  oddschecker_odds: "OddsChecker 赔率解析器",
  oddsportal_odds: "OddsPortal 赔率解析器",
  schema_org_schedule: "Schema.org 赛程解析器",
  sportsmole_injuries: "Sports Mole 伤停解析器",
  transfermarkt_injuries: "Transfermarkt 伤停解析器",
  transfermarkt_squads: "Transfermarkt 阵容解析器",
  world_football_elo: "Elo 评分解析器",
};

export function sourceNameLabel(sourceName: string) {
  return SOURCE_LABELS[sourceName] ?? sourceName.replaceAll("-", " ");
}

export function sourceAdapterLabel(adapter: string) {
  return ADAPTER_LABELS[adapter] ?? adapter.replaceAll("_", " ");
}
