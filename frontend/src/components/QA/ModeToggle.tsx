import type { QAMode } from '../../types/qa'

interface Props {
  mode: QAMode
  disabled?: boolean
  onChange: (m: QAMode) => void
}

export default function ModeToggle({ mode, disabled, onChange }: Props) {
  const base =
    'px-3 py-1 text-xs rounded border transition-colors disabled:opacity-50 disabled:cursor-not-allowed'
  return (
    <div className="flex items-center gap-1">
      <button
        className={
          `${base} ${
            mode === 'fast'
              ? 'bg-blue-50 dark:bg-blue-900/30 border-blue-300 dark:border-blue-600 text-blue-700 dark:text-blue-300'
              : 'border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800'
          }`
        }
        onClick={() => onChange('fast')}
        disabled={disabled}
        title="快速：单次 RAG 直接作答"
      >
        ⚡ 快速
      </button>
      <button
        className={
          `${base} ${
            mode === 'deep'
              ? 'bg-purple-50 dark:bg-purple-900/30 border-purple-300 dark:border-purple-600 text-purple-700 dark:text-purple-300'
              : 'border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800'
          }`
        }
        onClick={() => onChange('deep')}
        disabled={disabled}
        title="深度：Agent 工具循环，可见检索路径"
      >
        🔍 深度
      </button>
    </div>
  )
}
