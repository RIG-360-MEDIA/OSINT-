"use client";

import { useEffect, useState } from "react";

interface HealthData {
  status: string;
  version: string;
  db_connected: boolean;
  db_version: string | null;
  entity_count: number | null;
  source_count: number | null;
  environment: string;
}

export default function Home() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const apiUrl =
      process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

    fetch(`${apiUrl}/health`)
      .then((res) => res.json())
      .then((data: HealthData) => setHealth(data))
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <h1 className="text-4xl font-bold tracking-widest mb-2">
        RIG SURVEILLANCE
      </h1>
      <p className="text-gray-400 mb-8">System initialising.</p>

      {!health && !error && (
        <p className="text-gray-600 text-sm animate-pulse">
          Connecting to backend…
        </p>
      )}

      {error && (
        <div className="border border-red-800 p-4 rounded text-sm font-mono text-red-400">
          Backend unreachable: {error}
        </div>
      )}

      {health && (
        <div className="border border-gray-700 p-6 rounded text-sm font-mono space-y-2 min-w-64">
          <div>
            <span className="text-gray-500">db_connected: </span>
            <span
              className={
                health.db_connected ? "text-green-400" : "text-red-400"
              }
            >
              {String(health.db_connected)}
            </span>
          </div>
          <div>
            <span className="text-gray-500">entity_count: </span>
            <span className="text-blue-400">
              {health.entity_count ?? "—"}
            </span>
          </div>
          <div>
            <span className="text-gray-500">source_count: </span>
            <span className="text-blue-400">
              {health.source_count ?? "—"}
            </span>
          </div>
          <div>
            <span className="text-gray-500">environment: </span>
            <span className="text-yellow-400">{health.environment}</span>
          </div>
          <div>
            <span className="text-gray-500">version: </span>
            <span className="text-gray-300">{health.version}</span>
          </div>
        </div>
      )}
    </main>
  );
}
