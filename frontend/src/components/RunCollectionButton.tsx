import { useEffect, useRef, useState } from "react";
import { Play } from "lucide-react";
import { api } from "../lib/api";
import type { CollectionRun } from "../lib/types";
import { Button } from "./ui";

/** Starts a collection run and polls until it finishes, then calls onDone. */
export default function RunCollectionButton({
  onStarted,
  onDone,
  onError,
}: {
  onStarted?: (run: CollectionRun) => void;
  onDone?: (run: CollectionRun) => void;
  onError?: (msg: string) => void;
}) {
  const [running, setRunning] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current);
  }, []);

  async function poll(id: number) {
    try {
      const run = await api<CollectionRun>(`/collection/runs/${id}`);
      if (run.status === "running") {
        timer.current = window.setTimeout(() => poll(id), 2000);
        return;
      }
      setRunning(false);
      onDone?.(run);
    } catch (e) {
      setRunning(false);
      onError?.((e as Error).message);
    }
  }

  async function start() {
    setRunning(true);
    try {
      const run = await api<CollectionRun>("/collection/run", { method: "POST" });
      onStarted?.(run);
      poll(run.id);
    } catch (e) {
      setRunning(false);
      onError?.((e as Error).message);
    }
  }

  return (
    <Button onClick={start} loading={running}>
      {!running && <Play className="h-4 w-4" />}
      {running ? "Collecting…" : "Run collection now"}
    </Button>
  );
}
