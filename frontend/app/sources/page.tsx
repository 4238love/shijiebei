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

const implementedAdapters = new Set(["espn_scoreboard"]);

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

function groupByCategory(sources: SourceItem[]) {
  return sources.reduce<Record<string, SourceItem[]>>((groups, source) => {
    groups[source.category] = groups[source.category] ?? [];
    groups[source.category].push(source);
    return groups;
  }, {});
}

function adapterLabel(adapter: string) {
  return implementedAdapters.has(adapter) ? "live parser" : "configured";
}

export default async function SourcesPage() {
  const payload = await fetchSources();
  const groups = payload ? groupByCategory(payload.sources) : {};

  return (
    <main className="shell">
      <section className="hero source-hero">
        <p className="eyebrow">Source catalog</p>
        <h1>Live data intake map</h1>
        <p className="summary">
          First-wave crawl targets for schedule, form, rankings, injuries, odds,
          news sentiment, and player data. ESPN is wired as the first real JSON
          parser; heavyweight web pages stay configured until their adapters are
          implemented.
        </p>
      </section>

      {payload ? (
        <>
          <section className="source-health" aria-label="Source coverage">
            <article>
              <p className="label">Configured sources</p>
              <strong>{payload.sources.length}</strong>
            </article>
            <article>
              <p className="label">Missing categories</p>
              <strong>{payload.missing_first_wave_categories.length}</strong>
            </article>
            <article>
              <p className="label">Live parsers</p>
              <strong>
                {
                  payload.sources.filter((source) =>
                    implementedAdapters.has(source.adapter),
                  ).length
                }
              </strong>
            </article>
          </section>

          <section className="source-grid">
            {Object.entries(groups).map(([category, sources]) => (
              <article key={category} className="source-category">
                <div className="source-category-header">
                  <p className="label">{category.replace("_", " ")}</p>
                  <span>{sources.length} sources</span>
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
                        <p>{source.notes || source.url}</p>
                      </a>
                    ))}
                </div>
              </article>
            ))}
          </section>
        </>
      ) : (
        <section className="prediction-panel">
          <h2>Sources API unavailable</h2>
          <p className="summary compact">
            Start the backend service to inspect live data source configuration.
          </p>
        </section>
      )}
    </main>
  );
}
