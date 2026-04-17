"use client";

import { useEffect, useState, useCallback } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Types ─────────────────────────────────────────────────────────────────────

interface PanelState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  updatedAt: string | null;
}

function initPanel<T>(): PanelState<T> {
  return { data: null, error: null, loading: true, updatedAt: null };
}

interface PipelineHealth {
  total_articles: number;
  processed_normal: number;
  processed_low: number;
  processed_error: number;
  pending_nlp: number;
  pending_with_text: number;
  newest_article: string | null;
  oldest_pending: string | null;
  processing_rate_per_hour: number;
  pct_processed: number;
}

interface ArticleRow {
  id: string;
  title: string;
  source: string;
  language: string | null;
  topic: string | null;
  geo: string | null;
  nlp_processed: boolean;
  nlp_confidence: string | null;
  entity_count: number;
  collected_at: string | null;
}

interface RecentArticles {
  articles: ArticleRow[];
}

interface TopicItem { topic: string; count: number }
interface NlpQuality {
  total_processed: number;
  entity_extraction_rate: number;
  geo_tagging_rate: number;
  embedding_rate: number;
  non_english_count: number;
  topic_distribution: TopicItem[];
}

interface TierItem { tier: number; count: number; avg_score: number; max_score: number }
interface TopArticle {
  title: string; score: number; tier: number;
  explanation: string | null; topic: string | null; geo: string | null;
}
interface RelevanceQuality {
  tier_distribution: TierItem[];
  top_articles: TopArticle[];
}

interface DegradedSource {
  name: string; domain: string; health_score: number;
  consecutive_failures: number; last_collected: string | null;
}
interface SourceHealth {
  summary: {
    total: number; active: number; disabled: number; degraded: number;
    collected_last_hour: number; collected_today: number;
  };
  degraded_sources: DegradedSource[];
}

interface QueueStatus {
  worker_status: string;
  registered_task_count: number;
  active_task_count: number;
  nlp_queue_depth: number;
  scored_last_5min: number;
  scored_last_hour: number;
  relevance_pending_score: number;
}

interface IntelligenceStatus {
  users: { total: number; with_entities: number };
  briefs: { total: number; last_generated: string | null };
  top_entities_in_coverage: { entity: string; article_count: number }[];
}

interface GroqStatus {
  groq_status: {
    total_keys: number;
    available_keys: number;
    exhausted_keys: number;
  };
}

// ── Fetch helper ──────────────────────────────────────────────────────────────

async function fetchPanel<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const body = await res.text().catch(() => res.statusText);
    let msg = res.statusText;
    try { msg = JSON.parse(body).detail ?? msg; } catch { /* use statusText */ }
    throw new Error(`HTTP ${res.status}: ${msg}`);
  }
  return res.json() as Promise<T>;
}

function usePanel<T>(fetcher: () => Promise<T>, tick: number) {
  const [state, setState] = useState<PanelState<T>>(initPanel<T>());

  const run = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true }));
    try {
      const data = await fetcher();
      setState({ data, error: null, loading: false, updatedAt: new Date().toLocaleTimeString() });
    } catch (err: unknown) {
      setState((prev) => ({
        ...prev,
        error: err instanceof Error ? err.message : String(err),
        loading: false,
      }));
    }
  }, [fetcher]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    void run();
  }, [tick]); // eslint-disable-line react-hooks/exhaustive-deps

  return state;
}

// ── Panel shell ───────────────────────────────────────────────────────────────

function Panel({
  title,
  updatedAt,
  error,
  loading,
  children,
}: {
  title: string;
  updatedAt: string | null;
  error: string | null;
  loading: boolean;
  children: React.ReactNode;
}) {
  return (
    <div
      className={[
        "border rounded p-4 font-mono text-sm flex flex-col gap-2",
        error ? "border-red-600 bg-red-950/20" : "border-gray-700 bg-gray-950",
      ].join(" ")}
    >
      <div className="flex items-center justify-between">
        <span className="font-bold text-gray-200 tracking-wide">{title}</span>
        {updatedAt && (
          <span className="text-gray-600 text-xs">updated {updatedAt}</span>
        )}
      </div>
      {error ? (
        <p className="text-red-400 text-xs break-all">Error: {error}</p>
      ) : loading && !children ? (
        <p className="text-gray-600 animate-pulse">Loading…</p>
      ) : (
        <div className={loading ? "opacity-50 transition-opacity" : ""}>
          {children}
        </div>
      )}
    </div>
  );
}

// ── Utility components ────────────────────────────────────────────────────────

function Stat({ label, value, color = "text-blue-400" }: { label: string; value: React.ReactNode; color?: string }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-gray-500">{label}</span>
      <span className={color}>{value}</span>
    </div>
  );
}

function Bar({ pct, color = "bg-blue-600" }: { pct: number; color?: string }) {
  return (
    <div className="h-2 w-full bg-gray-800 rounded overflow-hidden">
      <div className={`h-full ${color} rounded`} style={{ width: `${Math.min(pct, 100)}%` }} />
    </div>
  );
}

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

// ── Panels ────────────────────────────────────────────────────────────────────

function PipelinePanel({ tick }: { tick: number }) {
  const s = usePanel<PipelineHealth>(
    useCallback(() => fetchPanel<PipelineHealth>("/debug/pipeline-health"), []),
    tick,
  );
  const d = s.data;
  const pendingColor =
    d && d.pending_nlp < 100
      ? "text-green-400"
      : d && d.pending_nlp <= 1000
        ? "text-yellow-400"
        : "text-red-400";

  return (
    <Panel title="01 — Pipeline Health" updatedAt={s.updatedAt} error={s.error} loading={s.loading}>
      {d && (
        <div className="space-y-1">
          <div className="text-3xl font-bold text-white mb-2">{d.total_articles.toLocaleString()}</div>
          <Stat label="processed normal" value={d.processed_normal.toLocaleString()} color="text-green-400" />
          <Stat label="processed low-conf" value={d.processed_low.toLocaleString()} color="text-yellow-400" />
          <Stat label="processed error" value={d.processed_error.toLocaleString()} color="text-red-400" />
          <Stat label="pending NLP" value={`${d.pending_nlp.toLocaleString()} (with text: ${d.pending_with_text.toLocaleString()})`} color={pendingColor} />
          <Stat label="relevance scored/hr" value={d.processing_rate_per_hour} color="text-blue-400" />
          <Stat label="newest article" value={timeAgo(d.newest_article)} />
          <Stat label="oldest pending" value={timeAgo(d.oldest_pending)} />
          <div className="mt-2 space-y-1">
            <div className="flex justify-between text-xs text-gray-500">
              <span>% processed</span>
              <span>{d.pct_processed}%</span>
            </div>
            <Bar pct={d.pct_processed} color={d.pct_processed > 50 ? "bg-green-600" : "bg-yellow-600"} />
          </div>
        </div>
      )}
    </Panel>
  );
}

function RecentArticlesPanel({ tick }: { tick: number }) {
  const s = usePanel<RecentArticles>(
    useCallback(() => fetchPanel<RecentArticles>("/debug/recent-articles"), []),
    tick,
  );
  const articles = s.data?.articles ?? [];

  return (
    <Panel title="02 — Recent Articles" updatedAt={s.updatedAt} error={s.error} loading={s.loading}>
      {articles.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="text-gray-500 border-b border-gray-800">
                <th className="text-left pb-1 pr-2">Title</th>
                <th className="text-left pb-1 pr-2">Source</th>
                <th className="text-center pb-1 pr-2">NLP</th>
                <th className="text-left pb-1 pr-2">Topic</th>
                <th className="text-right pb-1 pr-2">Ent</th>
                <th className="text-right pb-1">Age</th>
              </tr>
            </thead>
            <tbody>
              {articles.map((a) => (
                <tr key={a.id} className="border-b border-gray-900 hover:bg-gray-900">
                  <td className="py-0.5 pr-2 text-gray-300 max-w-[200px] truncate">
                    {a.title.slice(0, 60)}
                  </td>
                  <td className="py-0.5 pr-2 text-gray-500 truncate max-w-[80px]">{a.source}</td>
                  <td className="py-0.5 pr-2 text-center">
                    {a.nlp_processed
                      ? a.nlp_confidence === "error"
                        ? <span className="text-red-400">✗</span>
                        : <span className="text-green-400">✓</span>
                      : <span className="text-yellow-400">⏳</span>
                    }
                  </td>
                  <td className="py-0.5 pr-2 text-gray-500 truncate max-w-[80px]">{a.topic ?? "—"}</td>
                  <td className="py-0.5 pr-2 text-right text-gray-400">{a.entity_count}</td>
                  <td className="py-0.5 text-right text-gray-600">{timeAgo(a.collected_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function NlpQualityPanel({ tick }: { tick: number }) {
  const s = usePanel<NlpQuality>(
    useCallback(() => fetchPanel<NlpQuality>("/debug/nlp-quality"), []),
    tick,
  );
  const d = s.data;
  const maxTopicCount = d ? Math.max(...d.topic_distribution.map((t) => t.count), 1) : 1;

  return (
    <Panel title="03 — NLP Quality" updatedAt={s.updatedAt} error={s.error} loading={s.loading}>
      {d && (
        <div className="space-y-2">
          <Stat label="processed (normal)" value={d.total_processed.toLocaleString()} />
          <Stat label="entity extraction" value={`${d.entity_extraction_rate}%`} color={d.entity_extraction_rate > 70 ? "text-green-400" : "text-yellow-400"} />
          <Stat label="geo tagging" value={`${d.geo_tagging_rate}%`} />
          <Stat label="embedding coverage" value={`${d.embedding_rate}%`} />
          <Stat label="non-English articles" value={d.non_english_count} />
          <div className="pt-1 border-t border-gray-800">
            <p className="text-gray-600 text-xs mb-1">Topic distribution</p>
            {d.topic_distribution.slice(0, 10).map((t) => (
              <div key={t.topic} className="mb-0.5">
                <div className="flex justify-between text-xs text-gray-400 mb-0.5">
                  <span className="truncate max-w-[160px]">{t.topic}</span>
                  <span className="text-gray-600 ml-2">{t.count}</span>
                </div>
                <Bar pct={(t.count / maxTopicCount) * 100} color="bg-blue-800" />
              </div>
            ))}
          </div>
        </div>
      )}
    </Panel>
  );
}

function RelevancePanel({ tick }: { tick: number }) {
  const s = usePanel<RelevanceQuality>(
    useCallback(() => fetchPanel<RelevanceQuality>("/debug/relevance-quality"), []),
    tick,
  );
  const d = s.data;

  return (
    <Panel title="04 — Relevance Quality" updatedAt={s.updatedAt} error={s.error} loading={s.loading}>
      {d && (
        <div className="space-y-2">
          <div className="space-y-1">
            {d.tier_distribution.map((t) => (
              <div key={t.tier} className="flex justify-between text-xs">
                <span className="text-gray-500">Tier {t.tier}</span>
                <span className="text-gray-300">{t.count} articles</span>
                <span className="text-gray-500">avg {t.avg_score.toFixed(3)}</span>
              </div>
            ))}
          </div>
          <div className="pt-1 border-t border-gray-800">
            <p className="text-gray-600 text-xs mb-1">Top articles by score</p>
            {d.top_articles.slice(0, 5).map((a, i) => (
              <div key={i} className="mb-1 pb-1 border-b border-gray-900">
                <div className="flex justify-between gap-2">
                  <span className="text-gray-300 truncate max-w-[180px] text-xs">{a.title.slice(0, 50)}</span>
                  <span className={[
                    "text-xs shrink-0 px-1 rounded",
                    a.tier === 1 ? "bg-green-900 text-green-300" :
                    a.tier === 2 ? "bg-yellow-900 text-yellow-300" :
                    "bg-gray-800 text-gray-400"
                  ].join(" ")}>T{a.tier} {a.score.toFixed(3)}</span>
                </div>
                {i === 0 && a.explanation && (
                  <p className="text-gray-600 text-xs mt-0.5 italic line-clamp-2">{a.explanation}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </Panel>
  );
}

function SourceHealthPanel({ tick }: { tick: number }) {
  const s = usePanel<SourceHealth>(
    useCallback(() => fetchPanel<SourceHealth>("/debug/source-health"), []),
    tick,
  );
  const d = s.data;

  return (
    <Panel title="05 — Source Health" updatedAt={s.updatedAt} error={s.error} loading={s.loading}>
      {d && (
        <div className="space-y-2">
          <Stat label="total sources" value={d.summary.total} />
          <Stat label="active" value={d.summary.active} color="text-green-400" />
          <Stat label="disabled" value={d.summary.disabled} color="text-gray-500" />
          <Stat label="degraded (health < 0.7)" value={d.summary.degraded} color={d.summary.degraded > 0 ? "text-yellow-400" : "text-green-400"} />
          <Stat label="collected last hour" value={d.summary.collected_last_hour} />
          <Stat label="collected today" value={d.summary.collected_today} />
          {d.degraded_sources.length > 0 && (
            <div className="pt-1 border-t border-gray-800">
              <p className="text-gray-600 text-xs mb-1">Degraded sources</p>
              {d.degraded_sources.map((src) => (
                <div key={src.domain} className="mb-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-400 truncate max-w-[160px]">{src.name}</span>
                    <span className="text-red-400 shrink-0">{src.consecutive_failures} fails</span>
                  </div>
                  <Bar pct={src.health_score * 100} color="bg-red-800" />
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

function QueuePanel({ tick }: { tick: number }) {
  const s = usePanel<QueueStatus>(
    useCallback(() => fetchPanel<QueueStatus>("/debug/queue-status"), []),
    tick,
  );
  const d = s.data;
  const online = d?.worker_status === "online";

  return (
    <Panel title="06 — Queue Status" updatedAt={s.updatedAt} error={s.error} loading={s.loading}>
      {d && (
        <div className="space-y-1">
          <div className="flex items-center gap-2 mb-2">
            <span className={online ? "text-green-400" : "text-red-400"}>
              {online ? "● ONLINE" : "● OFFLINE"}
            </span>
            <span className="text-gray-600 text-xs">{d.worker_status !== "online" && d.worker_status !== "offline" ? d.worker_status : ""}</span>
          </div>
          <Stat label="NLP queue depth" value={d.nlp_queue_depth.toLocaleString()} color={d.nlp_queue_depth > 1000 ? "text-red-400" : d.nlp_queue_depth > 100 ? "text-yellow-400" : "text-green-400"} />
          <Stat label="scored last 5 min" value={d.scored_last_5min} />
          <Stat label="scored last hour" value={d.scored_last_hour} />
          <Stat label="relevance pending" value={d.relevance_pending_score.toLocaleString()} />
          <Stat label="registered tasks" value={d.registered_task_count} />
          <Stat label="active tasks" value={d.active_task_count} />
        </div>
      )}
    </Panel>
  );
}

function IntelligencePanel({ tick }: { tick: number }) {
  const s = usePanel<IntelligenceStatus>(
    useCallback(() => fetchPanel<IntelligenceStatus>("/debug/intelligence-status"), []),
    tick,
  );
  const d = s.data;
  const maxEntityCount = d ? Math.max(...d.top_entities_in_coverage.map((e) => e.article_count), 1) : 1;

  return (
    <Panel title="07 — Intelligence Status" updatedAt={s.updatedAt} error={s.error} loading={s.loading}>
      {d && (
        <div className="space-y-2">
          <Stat label="total users" value={d.users.total} />
          <Stat label="users with entities" value={d.users.with_entities} />
          <Stat label="total briefs" value={d.briefs.total} />
          <Stat label="last brief generated" value={timeAgo(d.briefs.last_generated)} />
          <div className="pt-1 border-t border-gray-800">
            <p className="text-gray-600 text-xs mb-1">Top entities in coverage</p>
            {d.top_entities_in_coverage.map((e) => (
              <div key={e.entity} className="mb-0.5">
                <div className="flex justify-between text-xs text-gray-400 mb-0.5">
                  <span className="truncate max-w-[160px]">{e.entity}</span>
                  <span className="text-gray-600 ml-2">{e.article_count}</span>
                </div>
                <Bar pct={(e.article_count / maxEntityCount) * 100} color="bg-indigo-800" />
              </div>
            ))}
          </div>
        </div>
      )}
    </Panel>
  );
}

// ── Groq status bar ───────────────────────────────────────────────────────────

function GroqStatusBar() {
  const [data, setData] = useState<GroqStatus | null>(null);

  useEffect(() => {
    const load = () => {
      fetchPanel<GroqStatus>("/debug/groq-status")
        .then(setData)
        .catch(() => setData(null));
    };
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, []);

  if (!data) return null;
  const g = data.groq_status;
  return (
    <span className="text-xs font-mono text-gray-500">
      GROQ {g.available_keys}/{g.total_keys} keys available
      {g.exhausted_keys > 0 && (
        <span className="text-yellow-400 ml-1">({g.exhausted_keys} exhausted)</span>
      )}
    </span>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DebugPage() {
  const [tick, setTick] = useState(0);
  const [countdown, setCountdown] = useState(30);

  useEffect(() => {
    // 30s data refresh
    const dataId = setInterval(() => {
      setTick((t) => t + 1);
      setCountdown(30);
    }, 30000);

    // 1s countdown display
    const countId = setInterval(() => {
      setCountdown((c) => (c > 1 ? c - 1 : c));
    }, 1000);

    return () => {
      clearInterval(dataId);
      clearInterval(countId);
    };
  }, []);

  const env = process.env.NEXT_PUBLIC_ENVIRONMENT ?? "development";

  return (
    <main className="min-h-screen bg-black text-white p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-2 mb-6 border-b border-gray-800 pb-4">
          <div>
            <h1 className="text-2xl font-bold tracking-widest text-white">
              RIG SURVEILLANCE
            </h1>
            <p className="text-gray-500 text-sm mt-1">Debug Dashboard</p>
          </div>
          <div className="flex flex-col items-end gap-1">
            <span className="text-xs font-mono text-gray-500">
              ENV: <span className={env === "production" ? "text-red-400" : "text-green-400"}>{env}</span>
              {" "}| refresh in{" "}
              <span className="text-yellow-400">{countdown}s</span>
            </span>
            <GroqStatusBar />
          </div>
        </div>

        {/* 2-column grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <PipelinePanel tick={tick} />
          <RecentArticlesPanel tick={tick} />
          <NlpQualityPanel tick={tick} />
          <RelevancePanel tick={tick} />
          <SourceHealthPanel tick={tick} />
          <QueuePanel tick={tick} />
          <IntelligencePanel tick={tick} />
        </div>
      </div>
    </main>
  );
}
