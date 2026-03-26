import { Position, Handle } from '@xyflow/react'
import { useTheme } from '../../i18n/ThemeContext'
import type { DiagramNodeData } from './types'

const GLOW = {
  gray: { boxShadow: '0 0 12px rgba(156,163,175,0.8), 0 0 30px rgba(156,163,175,0.5), 0 0 60px rgba(156,163,175,0.25)', border: 'none' },
  blue: { boxShadow: '0 0 12px rgba(59,130,246,0.8), 0 0 30px rgba(59,130,246,0.5), 0 0 60px rgba(59,130,246,0.25)', border: 'none' },
  purple: { boxShadow: '0 0 12px rgba(139,92,246,0.8), 0 0 30px rgba(139,92,246,0.5), 0 0 60px rgba(139,92,246,0.25)', border: 'none' },
}

/** 开始/结束节点 — 圆角胶囊形 */
function StartEndNode({ data, isStart }: { data: DiagramNodeData; isStart: boolean }) {
  const { isDark } = useTheme()

  return (
    <div
      className={`px-6 py-3 rounded-full border-2 text-center w-[160px] transition-shadow duration-300 ${
        isDark
          ? 'bg-gray-600 border-gray-500 text-white'
          : 'bg-gray-500 border-gray-400 text-white'
      }`}
      style={data.selected ? GLOW.gray : {}}
      title={data.description}
    >
      {isStart && <Handle type="source" position={Position.Bottom} className="!bg-gray-400 !w-2 !h-2" />}
      {!isStart && <Handle type="target" position={Position.Top} className="!bg-gray-400 !w-2 !h-2" />}
      <div className="text-sm font-semibold">{data.label}</div>
    </div>
  )
}

/** 处理步骤节点 — 矩形 */
function ProcessNode({ data }: { data: DiagramNodeData }) {
  const { isDark } = useTheme()
  const isExpandable = !!data.expandable

  const colorClass = isExpandable
    ? isDark
      ? 'bg-purple-600 border-purple-500 text-white'
      : 'bg-purple-500 border-purple-400 text-white'
    : isDark
      ? 'bg-blue-600 border-blue-500 text-white'
      : 'bg-blue-500 border-blue-400 text-white'

  const handleClass = isExpandable ? '!bg-purple-400 !w-2 !h-2' : '!bg-blue-400 !w-2 !h-2'
  const descClass = isExpandable ? 'text-purple-100' : 'text-blue-100'
  const glow = data.selected ? (isExpandable ? GLOW.purple : GLOW.blue) : {}

  return (
    <div
      className={`px-4 py-3 rounded-lg border-2 shadow-sm cursor-pointer w-[240px] overflow-hidden transition-shadow duration-300 ${colorClass}`}
      style={glow}
      title={`${data.label}\n${data.description || ''}`}
    >
      <Handle type="target" position={Position.Top} className={handleClass} />
      <div className="text-sm font-semibold text-center break-words line-clamp-2">{data.label}</div>
      {data.description && (
        <div className={`text-[10px] text-center mt-1 break-words line-clamp-2 ${descClass}`}>{data.description}</div>
      )}
      <Handle type="source" position={Position.Bottom} className={handleClass} />
    </div>
  )
}

/** 判断节点 — 菱形 */
function DecisionNode({ data }: { data: DiagramNodeData }) {
  const { isDark } = useTheme()

  return (
    <div className="relative w-[140px] h-[140px] flex items-center justify-center">
      <Handle type="target" position={Position.Top} className="!bg-blue-400 !w-2 !h-2" style={{ top: 0 }} />
      <div
        className={`absolute inset-0 rotate-45 rounded-md border-2 transition-shadow duration-300 ${
          isDark
            ? 'bg-blue-600 border-blue-500'
            : 'bg-blue-500 border-blue-400'
        }`}
        style={data.selected ? GLOW.blue : {}}
      />
      <div className="relative z-10 text-center px-2 text-white" title={data.description}>
        <div className="text-xs font-semibold leading-tight">{data.label}</div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-blue-400 !w-2 !h-2" style={{ bottom: 0 }} />
      <Handle type="source" position={Position.Right} id="no" className="!bg-blue-400 !w-2 !h-2" style={{ right: 0 }} />
    </div>
  )
}

/** 统一入口 */
export default function CustomNode({ data }: { data: DiagramNodeData }) {
  switch (data.nodeType) {
    case 'start':
      return <StartEndNode data={data} isStart={true} />
    case 'end':
      return <StartEndNode data={data} isStart={false} />
    case 'decision':
      return <DecisionNode data={data} />
    case 'process':
    default:
      return <ProcessNode data={data} />
  }
}
