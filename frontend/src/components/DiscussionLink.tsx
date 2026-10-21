import { Link } from "react-router";
import { useStats } from "../lib/forum";
import "../styles/forum.css";

/** Small card for a stock page: honest thread and reply counts for this company, linking to its discussion board. */
export function DiscussionLink({ symbol }: { symbol: string }) {
  const { data, isError } = useStats(symbol);
  if (isError) return null;
  const n = data?.threads ?? 0;
  return (
    <div className="fo-dl">
      <b>Discussion</b>
      <span>{!data ? "Loading…" : n === 0 ? "No discussions yet. Start the first one." : `${n} discussion${n === 1 ? "" : "s"} · ${data.replies} repl${data.replies === 1 ? "y" : "ies"}`}. Opinion only, not advice.</span>
      <Link className="btn" to={`/forum/c/${encodeURIComponent(symbol)}`}>Open discussion</Link>
    </div>
  );
}
