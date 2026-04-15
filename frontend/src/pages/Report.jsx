import { useState, useEffect } from 'react'
import { generateReport, listReports, getReport, deleteReport } from '../api'
import { FileText, Loader2, Plus, Download, Trash2, ChevronRight, Clock } from 'lucide-react'

function formatDate(isoStr) {
  const d = new Date(isoStr)
  return d.toLocaleString('zh-TW', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function renderMarkdown(text) {
  // 簡易 markdown 渲染：處理標題、粗體、表格、換行
  const lines = text.split('\n')
  const elements = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // 標題
    if (line.startsWith('### ')) {
      elements.push(<h3 key={i} className="text-base font-bold text-slate-800 mt-5 mb-2">{line.slice(4)}</h3>)
    } else if (line.startsWith('## ')) {
      elements.push(<h2 key={i} className="text-lg font-bold text-slate-800 mt-6 mb-2 pb-1 border-b border-slate-100">{line.slice(3)}</h2>)
    } else if (line.startsWith('# ')) {
      elements.push(<h1 key={i} className="text-xl font-bold text-slate-900 mt-2 mb-3">{line.slice(2)}</h1>)
    // 分隔線
    } else if (line.trim() === '---') {
      elements.push(<hr key={i} className="my-3 border-slate-200" />)
    // 表格
    } else if (line.startsWith('|')) {
      const tableLines = []
      while (i < lines.length && lines[i].startsWith('|')) {
        tableLines.push(lines[i])
        i++
      }
      const headers = tableLines[0].split('|').filter(c => c.trim() !== '').map(c => c.trim())
      const rows = tableLines.slice(2).map(l => l.split('|').filter(c => c.trim() !== '').map(c => c.trim()))
      elements.push(
        <div key={i} className="overflow-x-auto my-3">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="bg-slate-50">
                {headers.map((h, hi) => <th key={hi} className="px-3 py-2 text-left font-semibold text-slate-700 border border-slate-200">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, ri) => (
                <tr key={ri} className={ri % 2 === 0 ? 'bg-white' : 'bg-slate-50/50'}>
                  {row.map((cell, ci) => <td key={ci} className="px-3 py-2 text-slate-600 border border-slate-200">{cell}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
      continue
    // 列表
    } else if (line.match(/^[-*] /)) {
      const items = []
      while (i < lines.length && lines[i].match(/^[-*] /)) {
        items.push(lines[i].slice(2))
        i++
      }
      elements.push(
        <ul key={i} className="my-2 space-y-1 pl-4">
          {items.map((item, ii) => <li key={ii} className="text-slate-600 text-sm flex gap-2"><span className="text-blue-400 flex-shrink-0">•</span><span dangerouslySetInnerHTML={{ __html: item.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') }} /></li>)}
        </ul>
      )
      continue
    // 空行
    } else if (line.trim() === '') {
      elements.push(<div key={i} className="h-1" />)
    // 一般段落（支援粗體）
    } else {
      elements.push(
        <p key={i} className="text-sm text-slate-600 leading-relaxed"
          dangerouslySetInnerHTML={{ __html: line.replace(/\*\*(.*?)\*\*/g, '<strong class="text-slate-800">$1</strong>') }} />
      )
    }
    i++
  }
  return elements
}

export default function Report() {
  const [reports, setReports] = useState([])
  const [current, setCurrent] = useState(null)
  const [loading, setLoading] = useState(false)
  const [loadingList, setLoadingList] = useState(true)
  const [deletingId, setDeletingId] = useState(null)

  useEffect(() => {
    fetchList()
  }, [])

  const fetchList = async () => {
    setLoadingList(true)
    try {
      const list = await listReports()
      setReports(list)
      // 自動選取最新一份
      if (list.length > 0 && !current) {
        const latest = await getReport(list[0].id)
        setCurrent(latest)
      }
    } catch {
      // ignore
    }
    setLoadingList(false)
  }

  const handleGenerate = async () => {
    setLoading(true)
    try {
      const report = await generateReport()
      setCurrent(report)
      setReports(prev => [{ id: report.id, title: report.title, created_at: report.created_at, preview: report.content.slice(0, 100) }, ...prev])
    } catch (e) {
      alert('生成失敗：' + (e.response?.data?.detail || '請確認後端服務與 API Key'))
    }
    setLoading(false)
  }

  const handleSelect = async (id) => {
    if (current?.id === id) return
    try {
      const report = await getReport(id)
      setCurrent(report)
    } catch { /* ignore */ }
  }

  const handleDelete = async (id, e) => {
    e.stopPropagation()
    if (!confirm('確定要刪除這份報告嗎？')) return
    setDeletingId(id)
    try {
      await deleteReport(id)
      setReports(prev => prev.filter(r => r.id !== id))
      if (current?.id === id) setCurrent(null)
    } catch { /* ignore */ }
    setDeletingId(null)
  }

  const handleDownload = () => {
    if (!current) return
    const blob = new Blob([current.content], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${current.title}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="flex gap-5 h-[calc(100vh-80px)]">
      {/* 左側：歷史列表 */}
      <div className="w-56 flex-shrink-0 flex flex-col gap-3">
        <button
          onClick={handleGenerate}
          disabled={loading}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {loading ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
          {loading ? '生成中...' : '生成本週報告'}
        </button>

        <div className="flex-1 overflow-y-auto space-y-1">
          {loadingList && <p className="text-xs text-slate-400 text-center py-4">載入中...</p>}
          {!loadingList && reports.length === 0 && (
            <p className="text-xs text-slate-400 text-center py-8">尚無報告<br />點擊上方按鈕生成</p>
          )}
          {reports.map(r => (
            <div
              key={r.id}
              onClick={() => handleSelect(r.id)}
              className={`group relative p-3 rounded-xl cursor-pointer transition-colors border ${
                current?.id === r.id
                  ? 'bg-blue-50 border-blue-200'
                  : 'bg-white border-slate-100 hover:border-slate-200 hover:bg-slate-50'
              }`}
            >
              <div className="flex items-start justify-between gap-1">
                <div className="flex-1 min-w-0">
                  <p className={`text-xs font-semibold truncate ${current?.id === r.id ? 'text-blue-700' : 'text-slate-700'}`}>
                    {r.title}
                  </p>
                  <div className="flex items-center gap-1 mt-1">
                    <Clock size={10} className="text-slate-400" />
                    <span className="text-xs text-slate-400">{formatDate(r.created_at)}</span>
                  </div>
                </div>
                {current?.id === r.id && <ChevronRight size={13} className="text-blue-400 flex-shrink-0 mt-0.5" />}
              </div>
              <button
                onClick={(e) => handleDelete(r.id, e)}
                disabled={deletingId === r.id}
                className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-slate-300 hover:text-red-500 transition-all"
                title="刪除"
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* 右側：報告內容 */}
      <div className="flex-1 flex flex-col min-w-0">
        {loading && (
          <div className="flex-1 bg-white rounded-2xl shadow-sm border border-slate-100 flex flex-col items-center justify-center gap-4">
            <Loader2 size={40} className="text-blue-400 animate-spin" />
            <div className="text-center">
              <p className="text-slate-600 font-medium">AI 正在分析銷售數據...</p>
              <p className="text-slate-400 text-sm mt-1">約需 20–40 秒，請稍候</p>
            </div>
          </div>
        )}

        {!loading && !current && (
          <div className="flex-1 bg-white rounded-2xl shadow-sm border border-slate-100 flex flex-col items-center justify-center gap-3 text-center px-8">
            <FileText size={48} className="text-slate-200" />
            <p className="text-slate-500 font-medium">點擊左上角「生成本週報告」</p>
            <p className="text-slate-400 text-sm">包含業績摘要、暢銷分析、類別表現與行動建議</p>
          </div>
        )}

        {!loading && current && (
          <div className="flex-1 flex flex-col bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
            {/* 報告標頭 */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 flex-shrink-0">
              <div className="flex items-center gap-2">
                <FileText size={16} className="text-blue-500" />
                <span className="font-semibold text-slate-700">{current.title}</span>
                <span className="text-xs text-slate-400">· {formatDate(current.created_at)}</span>
              </div>
              <button
                onClick={handleDownload}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-slate-600 hover:bg-slate-50 border border-slate-200 hover:border-slate-300 transition-colors"
              >
                <Download size={14} />
                下載 .md
              </button>
            </div>
            {/* 報告本文 */}
            <div className="flex-1 overflow-y-auto px-6 py-5">
              {renderMarkdown(current.content)}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
