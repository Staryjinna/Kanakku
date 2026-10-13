import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatINR } from "../api";

export interface CategoryDatum {
  category: string;
  total_paise: number;
}

const INK = "#334155";
const MUTED = "#64748b";
const BAR = "#047857"; // emerald-700, 5.5:1 against white

/** Indian short form: 12.5k, 3.2L (lakh), 1.4Cr (crore). */
function compact(paise: number): string {
  const r = paise / 100;
  const fmt = (n: number) => String(Math.round(n * 10) / 10);
  if (r >= 1e7) return `₹${fmt(r / 1e7)}Cr`;
  if (r >= 1e5) return `₹${fmt(r / 1e5)}L`;
  if (r >= 1e3) return `₹${fmt(r / 1e3)}k`;
  return `₹${Math.round(r)}`;
}

/** One series, so no legend: the heading names the measure. A table below carries every value. */
export function CategoryChart({ data, title }: { data: CategoryDatum[]; title: string }) {
  const total = data.reduce((a, d) => a + d.total_paise, 0);
  return (
    <figure aria-label={title}>
      <div style={{ height: data.length * 40 + 16 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 0, right: 56, bottom: 0, left: 0 }} barCategoryGap={10}>
            <XAxis type="number" hide domain={[0, "dataMax"]} />
            <YAxis type="category" dataKey="category" width={104} axisLine={false} tickLine={false}
              tick={{ fill: INK, fontSize: 12 }} />
            <Tooltip cursor={{ fill: "rgba(148,163,184,0.15)" }}
              formatter={(v) => [formatINR(Number(v)), "Spent"]}
              contentStyle={{ fontSize: 12, borderRadius: 6, border: "1px solid #e2e8f0" }} />
            <Bar dataKey="total_paise" fill={BAR} barSize={14} radius={[0, 4, 4, 0]} isAnimationActive={false}>
              <LabelList dataKey="total_paise" position="right" fill={MUTED} fontSize={11}
                formatter={(v) => compact(Number(v))} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <table className="mt-3 w-full text-xs">
        <caption className="sr-only">{title}</caption>
        <thead className="sr-only"><tr><th>Category</th><th>Amount</th><th>Share</th></tr></thead>
        <tbody className="divide-y divide-slate-100">
          {data.map((d) => (
            <tr key={d.category}>
              <td className="py-1 capitalize text-slate-700">{d.category}</td>
              <td className="py-1 text-right tabular-nums text-slate-700">{formatINR(d.total_paise)}</td>
              <td className="w-12 py-1 text-right tabular-nums text-slate-500">{total ? Math.round((d.total_paise / total) * 100) : 0}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
