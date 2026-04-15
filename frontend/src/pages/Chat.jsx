import { useState, useRef, useEffect } from 'react'
import { sendChat, getChatHistory, clearChatHistory } from '../api'
import { Send, Bot, User, Sparkles, Trash2, Clock } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const SUGGESTIONS = [
  '本週哪個類別賣得最好？',
  '目前有哪些商品需要補貨？',
  '本週跟上週相比業績如何？',
  '本月總營收是多少？',
  '哪個商品的銷售表現最差？',
  '請分析一下整體銷售趨勢',
]

const WELCOME = { role: 'assistant', content: '你好！我是你的 AI 商業分析助理。我已載入最新的銷售與商品資料，你可以用自然語言問我任何業績相關的問題。' }

function formatTime(isoStr) {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  return d.toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export default function Chat() {
  const [messages, setMessages] = useState([WELCOME])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingHistory, setLoadingHistory] = useState(true)
  const bottomRef = useRef(null)

  // 頁面載入時從後端拉取歷史
  useEffect(() => {
    getChatHistory()
      .then(d => {
        if (d.messages && d.messages.length > 0) {
          setMessages([WELCOME, ...d.messages])
        }
      })
      .catch(() => {/* 無歷史或錯誤 */})
      .finally(() => setLoadingHistory(false))
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const send = async (text) => {
    const q = (text || input).trim()
    if (!q || loading) return
    setInput('')
    const newMessages = [...messages, { role: 'user', content: q }]
    setMessages(newMessages)
    setLoading(true)
    try {
      // 只傳最近 10 輪對話給 AI（去掉 WELCOME 那筆）
      const history = newMessages.slice(1).slice(-20)
      const res = await sendChat(q, history)
      setMessages(prev => [...prev, { role: 'assistant', content: res.answer }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: '⚠️ 無法連線到 AI 服務，請確認後端已啟動並設定 ANTHROPIC_API_KEY。' }])
    }
    setLoading(false)
  }

  const handleClear = async () => {
    if (!confirm('確定要清空所有對話記錄嗎？')) return
    try {
      await clearChatHistory()
      setMessages([WELCOME])
    } catch { /* ignore */ }
  }

  const isOnlyWelcome = messages.length <= 1

  return (
    <div className="flex flex-col h-[calc(100vh-80px)]">
      {/* 標題列 */}
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <h2 className="text-xl font-bold text-slate-800">AI 問答分析</h2>
        <div className="flex items-center gap-2">
          {!isOnlyWelcome && (
            <button
              onClick={handleClear}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-slate-500 hover:text-red-500 hover:bg-red-50 border border-slate-200 hover:border-red-200 transition-colors"
            >
              <Trash2 size={13} />
              清空記錄
            </button>
          )}
          <div className="flex items-center gap-2 text-sm text-blue-600 bg-blue-50 px-3 py-1.5 rounded-full">
            <Sparkles size={14} />
            由 Claude AI 驅動
          </div>
        </div>
      </div>

      {/* 快速建議（只在無歷史時顯示） */}
      {isOnlyWelcome && !loadingHistory && (
        <div className="mb-4 flex-shrink-0">
          <p className="text-xs text-slate-400 mb-2">快速問題建議</p>
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map(s => (
              <button
                key={s}
                onClick={() => send(s)}
                className="px-3 py-1.5 bg-white border border-slate-200 rounded-full text-sm text-slate-600 hover:border-blue-300 hover:text-blue-600 transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 對話區 */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1 scrollbar-thin">
        {loadingHistory && (
          <p className="text-xs text-slate-400 text-center py-4">載入對話歷史...</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex items-start gap-3 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
              m.role === 'user' ? 'bg-blue-600' : 'bg-slate-100'
            }`}>
              {m.role === 'user' ? <User size={15} className="text-white" /> : <Bot size={15} className="text-slate-600" />}
            </div>
            <div className="flex flex-col gap-1 max-w-[75%]">
              <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                m.role === 'user'
                  ? 'bg-blue-600 text-white rounded-tr-sm whitespace-pre-wrap'
                  : 'bg-white text-slate-700 border border-slate-100 rounded-tl-sm shadow-sm prose prose-sm max-w-none prose-table:text-xs'
              }`}>
                {m.role === 'user' ? m.content : (
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      table: ({node, ...props}) => <table className="border-collapse w-full my-2" {...props} />,
                      th: ({node, ...props}) => <th className="border border-slate-200 bg-slate-50 px-2 py-1 text-left font-semibold" {...props} />,
                      td: ({node, ...props}) => <td className="border border-slate-200 px-2 py-1" {...props} />,
                      strong: ({node, ...props}) => <strong className="font-semibold text-slate-900" {...props} />,
                      h1: ({node, ...props}) => <h1 className="text-base font-bold mt-3 mb-1" {...props} />,
                      h2: ({node, ...props}) => <h2 className="text-sm font-bold mt-2 mb-1" {...props} />,
                      h3: ({node, ...props}) => <h3 className="text-sm font-semibold mt-2 mb-1" {...props} />,
                      ul: ({node, ...props}) => <ul className="list-disc pl-4 my-1 space-y-0.5" {...props} />,
                      ol: ({node, ...props}) => <ol className="list-decimal pl-4 my-1 space-y-0.5" {...props} />,
                      li: ({node, ...props}) => <li className="leading-relaxed" {...props} />,
                      hr: ({node, ...props}) => <hr className="my-2 border-slate-200" {...props} />,
                      code: ({node, inline, ...props}) => inline
                        ? <code className="bg-slate-100 px-1 rounded text-xs font-mono" {...props} />
                        : <code className="block bg-slate-100 p-2 rounded text-xs font-mono my-1 overflow-x-auto" {...props} />,
                    }}
                  >
                    {m.content}
                  </ReactMarkdown>
                )}
              </div>
              {m.created_at && (
                <div className={`flex items-center gap-1 text-xs text-slate-400 ${m.role === 'user' ? 'justify-end' : ''}`}>
                  <Clock size={10} />
                  {formatTime(m.created_at)}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex items-start gap-3">
            <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center flex-shrink-0">
              <Bot size={15} className="text-slate-600" />
            </div>
            <div className="bg-white border border-slate-100 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
              <div className="flex gap-1.5">
                {[0, 1, 2].map(i => (
                  <div key={i} className="w-2 h-2 bg-slate-300 rounded-full animate-bounce"
                    style={{ animationDelay: `${i * 0.15}s` }} />
                ))}
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* 輸入列 */}
      <div className="mt-4 flex-shrink-0">
        <div className="flex gap-3 bg-white border border-slate-200 rounded-2xl p-2 shadow-sm focus-within:border-blue-300 transition-colors">
          <input
            className="flex-1 px-3 py-2 text-sm outline-none bg-transparent text-slate-800 placeholder-slate-400"
            placeholder="輸入問題（Enter 送出，Shift+Enter 換行）"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), send())}
            disabled={loading}
          />
          <button
            onClick={() => send()}
            disabled={!input.trim() || loading}
            className="px-4 py-2 bg-blue-600 text-white rounded-xl text-sm font-medium disabled:opacity-40 hover:bg-blue-700 transition-colors flex items-center gap-2"
          >
            <Send size={15} />
            送出
          </button>
        </div>
      </div>
    </div>
  )
}
