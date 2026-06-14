const TEAM_NAME_PAIRS = [
  ["Argentina", "阿根廷"],
  ["Australia", "澳大利亚"],
  ["Austria", "奥地利"],
  ["Belgium", "比利时"],
  ["Brazil", "巴西"],
  ["Cape Verde", "佛得角"],
  ["Cameroon", "喀麦隆"],
  ["Canada", "加拿大"],
  ["Chile", "智利"],
  ["Colombia", "哥伦比亚"],
  ["Costa Rica", "哥斯达黎加"],
  ["Croatia", "克罗地亚"],
  ["Curacao", "库拉索"],
  ["Curaçao", "库拉索"],
  ["Czech Republic", "捷克"],
  ["Czechia", "捷克"],
  ["Denmark", "丹麦"],
  ["Ecuador", "厄瓜多尔"],
  ["Egypt", "埃及"],
  ["England", "英格兰"],
  ["France", "法国"],
  ["Germany", "德国"],
  ["Ghana", "加纳"],
  ["Haiti", "海地"],
  ["Honduras", "洪都拉斯"],
  ["Iran", "伊朗"],
  ["Italy", "意大利"],
  ["Ivory Coast", "科特迪瓦"],
  ["Japan", "日本"],
  ["Jordan", "约旦"],
  ["Mexico", "墨西哥"],
  ["Morocco", "摩洛哥"],
  ["Netherlands", "荷兰"],
  ["New Zealand", "新西兰"],
  ["Nigeria", "尼日利亚"],
  ["Norway", "挪威"],
  ["Panama", "巴拿马"],
  ["Paraguay", "巴拉圭"],
  ["Peru", "秘鲁"],
  ["Poland", "波兰"],
  ["Portugal", "葡萄牙"],
  ["Qatar", "卡塔尔"],
  ["Saudi Arabia", "沙特阿拉伯"],
  ["Senegal", "塞内加尔"],
  ["Serbia", "塞尔维亚"],
  ["South Africa", "南非"],
  ["South Korea", "韩国"],
  ["Spain", "西班牙"],
  ["Switzerland", "瑞士"],
  ["Tunisia", "突尼斯"],
  ["USA", "美国"],
  ["United States", "美国"],
  ["Uruguay", "乌拉圭"],
  ["Uzbekistan", "乌兹别克斯坦"],
  ["Venezuela", "委内瑞拉"],
  ["Wales", "威尔士"],
] as const;

const TEAM_LABELS_BY_KEY = Object.fromEntries(
  TEAM_NAME_PAIRS.map(([englishName, chineseName]) => [
    normalizeTeamKey(englishName),
    chineseName,
  ]),
) as Record<string, string>;

const TEAM_CANONICAL_BY_LABEL = Object.fromEntries(
  TEAM_NAME_PAIRS.map(([englishName, chineseName]) => [chineseName, englishName]),
) as Record<string, string>;

export function teamLabel(teamName: string) {
  const trimmedTeamName = teamName.trim();
  return TEAM_LABELS_BY_KEY[normalizeTeamKey(trimmedTeamName)] ?? trimmedTeamName;
}

export function canonicalTeamName(teamName: string) {
  const trimmedTeamName = teamName.trim();
  return TEAM_CANONICAL_BY_LABEL[trimmedTeamName] ?? trimmedTeamName;
}

export function matchLabel(homeTeam: string, awayTeam: string) {
  return `${teamLabel(homeTeam)} 对 ${teamLabel(awayTeam)}`;
}

export function matchTextLabel(matchText: string) {
  const match = matchText.match(/^(.+?)\s+(?:vs\.?|v)\s+(.+)$/i);
  if (!match) {
    return localizeTeamNamesInText(matchText);
  }
  return matchLabel(match[1], match[2]);
}

export function localizeTeamNamesInText(text: string) {
  return TEAM_NAME_PAIRS.reduce(
    (localizedText, [englishName, chineseName]) =>
      localizedText.replace(
        new RegExp(`\\b${escapeRegExp(englishName)}\\b`, "gi"),
        chineseName,
      ),
    text,
  );
}

function normalizeTeamKey(teamName: string) {
  return teamName.trim().toLowerCase();
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
