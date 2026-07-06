import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { HourlyBucket } from "../types";

function formatHour(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function HourlyTradeChart({ data }: { data: HourlyBucket[] }) {
  if (data.length === 0) {
    return <p className="muted">No trade recorded yet today.</p>;
  }

  const chartData = data.map((bucket) => ({
    hour: formatHour(bucket.hour),
    sales: Number(bucket.total_sales),
    count: bucket.sale_count,
  }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="hour" />
        <YAxis />
        <Tooltip formatter={(value) => [`$${Number(value).toFixed(2)}`, "Sales"]} />
        <Bar dataKey="sales" fill="#3b6fd6" />
      </BarChart>
    </ResponsiveContainer>
  );
}
