import { ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";
import type { Item } from "../lib/types";
import { timeAgo } from "../lib/format";
import { Badge } from "./ui";

export default function ItemRow({ item, showCompany = true }: { item: Item; showCompany?: boolean }) {
  return (
    <li className="py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <a href={item.url} target="_blank" rel="noopener noreferrer" className="group text-sm font-medium text-slate-800 hover:text-indigo-600">
            {item.title}
            <ExternalLink className="ml-1 inline h-3 w-3 opacity-0 transition group-hover:opacity-100" />
          </a>
          {item.summary && <p className="mt-0.5 line-clamp-2 text-xs text-slate-500">{item.summary}</p>}
          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
            {showCompany && (
              <Link to={`/companies/${item.company_id}`} className="font-medium text-slate-700 hover:text-indigo-600">
                {item.company_name}
              </Link>
            )}
            <span>{item.domain ?? item.source}</span>
            <span>·</span>
            <span>{item.source}</span>
            {item.score != null && (
              <>
                <span>·</span>
                <span>{item.score} pts</span>
              </>
            )}
            {item.categories.map((c) => (
              <Badge key={c}>{c}</Badge>
            ))}
          </div>
        </div>
        <span className="shrink-0 whitespace-nowrap text-xs text-slate-400">{timeAgo(item.published_at)}</span>
      </div>
    </li>
  );
}
