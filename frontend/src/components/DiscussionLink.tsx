import { Link } from "react-router";
import { BOARD_NAME, forumMe, useStats } from "../lib/forum";
import "../styles/forum.css";

/** Small card for a stock page: honest thread and reply counts for this company, linking to its discussion board. */
export function DiscussionLink({ symbol }: { symbol: string }) {
  const { data, isError } = useStats(symbol);
  const { data: me } = forumMe();
  if (isError) return null;
  const n = data?.threads ?? 0;
  if (me && !me.signedIn) return (
    <div className="fo-dl">
      <b>Discussion</b>
      <span>Basic, Silver and Gold members each have their own board. Sign in (free) to see yours. Opinion only, not advice.</span>
      <Link className="btn" to={`/login?next=${encodeURIComponent(`/forum/c/${symbol}`)}`}>Sign in</Link>
    </div>
  );
  return (
    <div className="fo-dl">
      <b>Discussion{me?.board ? ` · ${BOARD_NAME[me.board]} board` : ""}</b>
      <span>{!data ? "Loading…" : n === 0 ? "No discussions yet. Start the first one." : `${n} discussion${n === 1 ? "" : "s"} · ${data.replies} repl${data.replies === 1 ? "y" : "ies"}`}. Opinion only, not advice.</span>
      <Link className="btn" to={`/forum/c/${encodeURIComponent(symbol)}`}>Open discussion</Link>
    </div>
  );
}
