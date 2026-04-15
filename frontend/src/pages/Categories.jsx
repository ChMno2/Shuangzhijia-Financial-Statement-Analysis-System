import { useEffect, useState } from 'react'
import { getCategorySales } from '../api'
import {
  PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid
} from 'recharts'

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4', '#84cc16']
const fmt = (n) => `NT$ ${Number(n || 0).toLocaleString()}`

const renderCustomLabel = ({ cx, cy, midAngle, innerRadius, outerRadius, percent }) => {
  if (percent < 0.04) return null
  const RADIAN = Math.PI / 180
  const radius = innerRadius + (outerRadius - innerRadius) * 0.5
  const x = cx + radius * Math.cos(-midAngle * RADIAN)
  const y = cy + radius * Math.sin(-midAngle * RADIAN)
  return (
    <text x={x} y={y} fill="white" textAnchor="middle" dominantBaseline="central" fontSize={13} fontWeight={600}>
      {`${(percent * 100).toFixed(1)}%`}
    </text>
  )
}

export default function Categories() {
  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getCategorySales().then(d => { setData(d.category_sales || []); setLoading(false) })
  }, [])

  const total = data.reduce((s, d) => s + Number(d.revenue), 0)

  if (loading) return <div className="p-8 text-slate-500">載入中...</div>

  return (
    <div className="space-y-5">
      <h2 className="text-xl font-bold text-slate-800">類別銷售分析</h2>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {/* 圓餅圖 */}
        <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100">
          <h3 className="font-semibold text-slate-700 mb-4">銷售佔比</h3>
          <ResponsiveContainer width="100%" height={320}>
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={renderCustomLabel}
                outerRadius={130}
                dataKey="revenue"
                nameKey="category"
              >
                {data.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={v => fmt(v)} />
              <Legend formatter={v => <span className="text-sm text-slate-600">{v}</span>} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* 長條圖 */}
        <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100">
          <h3 className="font-semibold text-slate-700 mb-4">各類別營收比較</h3>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={data} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={v => `${(v / 1000).toFixed(0)}K`} />
              <YAxis type="category" dataKey="category" tick={{ fontSize: 12 }} width={60} />
              <Tooltip formatter={v => fmt(v)} />
              <Bar dataKey="revenue" radius={[0, 4, 4, 0]} name="營收">
                {data.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 類別明細表 */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-100">
              <th className="text-left px-5 py-3 text-slate-500 font-medium">類別</th>
              <th className="text-right px-5 py-3 text-slate-500 font-medium">營收</th>
              <th className="text-right px-5 py-3 text-slate-500 font-medium">佔比</th>
              <th className="px-5 py-3 text-slate-500 font-medium">比例條</th>
            </tr>
          </thead>
          <tbody>
            {[...data].sort((a, b) => b.revenue - a.revenue).map((d, i) => (
              <tr key={i} className="border-b border-slate-50 hover:bg-slate-50/50">
                <td className="px-5 py-3">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
                    <span className="font-medium text-slate-700">{d.category}</span>
                  </div>
                </td>
                <td className="px-5 py-3 text-right font-medium text-slate-800">{fmt(d.revenue)}</td>
                <td className="px-5 py-3 text-right text-slate-600">{d.percentage}%</td>
                <td className="px-5 py-3 w-40">
                  <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{ width: `${d.percentage}%`, background: COLORS[i % COLORS.length] }}
                    />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-slate-200 bg-slate-50">
              <td className="px-5 py-3 font-bold text-slate-700">合計</td>
              <td className="px-5 py-3 text-right font-bold text-slate-800">{fmt(total)}</td>
              <td className="px-5 py-3 text-right font-bold text-slate-700">100%</td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  )
}
