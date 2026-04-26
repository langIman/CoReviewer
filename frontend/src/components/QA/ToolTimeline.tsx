import { useMemo, useState } from 'react'
import type { ToolEvent } from '../../types/qa'

interface Props {
  events: ToolEvent[]
  budgetExhausted?: boolean
}

interface CombinedRow {
  iteration: number
  name: string
  args_preview?: unknown
  ok?: boolean
  preview?: string
  done: boolean
}

function combine(events: ToolEvent[]): CombinedRow[] {
  const rows: CombinedRow[] = []
  for (const e of events) {
    if (e.phase === 'call') {
      rows.push({
        iteration: e.iteration,
        name: e.name,
        args_preview: e.args_preview,
        done: false,
      })
    } else {
      // result → find matching call
      const target = [...rows]
        .reverse()
        .find((r) => r.iteration === e.iteration && r.name === e.name && !r.done)
      if (target) {
        target.ok = e.ok
        target.preview = e.preview
        target.done = true
      } else {
        rows.push({
          iteration: e.iteration,
          name: e.name,
          ok: e.ok,
          preview: e.preview,
          done: true,
        })
      }
    }
  }
  return rows
}

function previewJson(v: unknown, max = 200): string {
  try {
    const s = typeof v === 'string' ? v : JSON.stringify(v)
    return s.length > max ? s.slice(0, max) + '…' : s
  } catch {
    return String(v)
  }
}

export default function ToolTimeline({ events, budgetExhausted }: Props) {
  const rows = useMemo(() => combine(events), [events])
  const [open, setOpen] = useState(false)

  if (rows.length === 0 && !budgetExhausted) return null

  const activeCount = rows.filter((r) => r.done).length
  const total = rows.length
  const label = total > 0 ? `🔧 ${activeCount}/${total} 次工具调用` : '🔧 工具调用'

  return (
    <div className="my-2 border border-gray-200 dark:border-gray-700 rounded bg-gray-50 dark:bg-gray-800/60">
      <button
        className="w-full text-left px-3 py-1.5 text-xs text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 flex items-center justify-between"
        onClick={() => setOpen((v) => !v)}
      >
        <span>{label}</span>
        <span className="text-gray-400">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="px-3 py-2 border-t border-gray-200 dark:border-gray-700 space-y-2">
          {rows.map((r, idx) => (
            <div key={idx} className="text-xs font-mono">
              <div className="flex items-center gap-2 text-gray-700 dark:text-gray-300">
                <span className="text-gray-400">#{r.iteration}</span>
                <span className="font-semibold">{r.name}</span>
                {r.done ? (
                  r.ok ? (
                    <span className="text-green-600 dark:text-green-400">✓</span>
                  ) : (
                    <span className="text-red-600 dark:text-red-400">✗</span>
                  )
                ) : (
                  <span className="text-blue-500 animate-pulse">…</span>
                )}
              </div>
              {r.args_preview !== undefined && (
                <div className="pl-5 text-gray-500 dark:text-gray-400 whitespace-pre-wrap break-words">
                  args: {previewJson(r.args_preview, 200)}
                </div>
              )}
              {r.preview && (
                <div className="pl-5 text-gray-500 dark:text-gray-400 whitespace-pre-wrap break-words">
                  → {previewJson(r.preview, 300)}
                </div>
              )}
            </div>
          ))}
          {budgetExhausted && (
            <div className="text-xs px-2 py-1.5 bg-yellow-50 dark:bg-yellow-900/30 border border-yellow-200 dark:border-yellow-700 rounded text-yellow-800 dark:text-yellow-200">
              ⚠ Token 预算已耗尽，AI 正在基于已收集信息作答
            </div>
          )}
        </div>
      )}
    </div>
  )
}
