import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { shortDate } from "../lib/format";
import { EmptyState } from "./ui";

export const PALETTE = ["#4f46e5", "#0ea5e9", "#f59e0b", "#10b981", "#ec4899", "#8b5cf6", "#ef4444", "#14b8a6"];

const tooltipStyle = {
  contentStyle: { borderRadius: 8, border: "1px solid #e2e8f0", fontSize: 12, boxShadow: "0 4px 12px rgba(0,0,0,.06)" },
};

export function ActivityChart({ data, height = 260 }: { data: { date: string; count: number }[]; height?: number }) {
  if (!data.some((d) => d.count > 0)) return <EmptyState title="No activity yet" description="Collected items will appear here over time." />;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 5, right: 8, left: -18, bottom: 0 }}>
        <defs>
          <linearGradient id="activityFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#4f46e5" stopOpacity={0.25} />
            <stop offset="100%" stopColor="#4f46e5" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#f1f5f9" vertical={false} />
        <XAxis dataKey="date" tickFormatter={shortDate} tickLine={false} axisLine={false} minTickGap={24} />
        <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
        <Tooltip {...tooltipStyle} labelFormatter={(l) => shortDate(String(l))} formatter={(v) => [v, "Items"]} />
        <Area isAnimationActive={false} type="monotone" dataKey="count" stroke="#4f46e5" strokeWidth={2} fill="url(#activityFill)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function HBarChart({
  data,
  dataKey,
  labelKey,
  height,
  color = "#4f46e5",
  valueLabel = "Items",
}: {
  data: Record<string, string | number>[];
  dataKey: string;
  labelKey: string;
  height?: number;
  color?: string;
  valueLabel?: string;
}) {
  if (!data.length || !data.some((d) => Number(d[dataKey]) > 0)) return <EmptyState title="No data for this period" />;
  const h = height ?? Math.max(160, data.length * 34 + 30);
  return (
    <ResponsiveContainer width="100%" height={h}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, left: 8, bottom: 0 }}>
        <CartesianGrid stroke="#f1f5f9" horizontal={false} />
        <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={false} />
        <YAxis type="category" dataKey={labelKey} width={130} tickLine={false} axisLine={false} />
        <Tooltip {...tooltipStyle} cursor={{ fill: "#f8fafc" }} formatter={(v) => [v, valueLabel]} />
        <Bar isAnimationActive={false} dataKey={dataKey} fill={color} radius={[0, 4, 4, 0]} barSize={18} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function TrendChart({ data }: { data: { term: string; count: number; previous: number }[] }) {
  if (!data.length) return <EmptyState title="Not enough data for trends" description="Trends appear once terms repeat across several headlines." />;
  return (
    <ResponsiveContainer width="100%" height={Math.max(200, data.length * 30 + 50)}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, left: 8, bottom: 0 }}>
        <CartesianGrid stroke="#f1f5f9" horizontal={false} />
        <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={false} />
        <YAxis type="category" dataKey="term" width={130} tickLine={false} axisLine={false} />
        <Tooltip {...tooltipStyle} cursor={{ fill: "#f8fafc" }} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar isAnimationActive={false} dataKey="count" name="This period" fill="#4f46e5" radius={[0, 4, 4, 0]} barSize={10} />
        <Bar isAnimationActive={false} dataKey="previous" name="Previous period" fill="#cbd5e1" radius={[0, 4, 4, 0]} barSize={10} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function TokensChart({ data }: { data: { date: string; input_tokens: number; output_tokens: number }[] }) {
  if (!data.length) return <EmptyState title="No AI usage yet" description="Run an analysis to see token usage." />;
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 5, right: 8, left: -10, bottom: 0 }}>
        <CartesianGrid stroke="#f1f5f9" vertical={false} />
        <XAxis dataKey="date" tickFormatter={shortDate} tickLine={false} axisLine={false} />
        <YAxis tickLine={false} axisLine={false} />
        <Tooltip {...tooltipStyle} labelFormatter={(l) => shortDate(String(l))} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar isAnimationActive={false} dataKey="input_tokens" name="Input tokens" stackId="t" fill="#4f46e5" />
        <Bar isAnimationActive={false} dataKey="output_tokens" name="Output tokens" stackId="t" fill="#0ea5e9" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
