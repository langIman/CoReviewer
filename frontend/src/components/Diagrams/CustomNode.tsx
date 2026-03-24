import { Position, Handle } from '@xyflow/react'
import { useTheme } from '../../i18n/ThemeContext'
import type { DiagramNodeData } from './types'

const GLOW = {
  gray: { boxShadow: '0 0 12px rgba(156,163,175,0.8), 0 0 30px rgba(156,163,175,0.5), 0 0 60px rgba(156,163,175,0.25)', border: 'none' },
  blue: { boxShadow: '0 0 12px rgba(59,130,246,0.8), 0 0 30px rgba(59,130,246,0.5), 0 0 60px rgba(59,130,246,0.25)', border: 'none' },
  amber: { boxShadow: '0 0 12px rgba(245,158,11,0.8), 0 0 30px rgba(245,158,11,0.5), 0 0 60px rgba(245,158,11,0.25)', border: 'none' },
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

  return (
    <div
      className={`px-4 py-3 rounded-lg border-2 shadow-sm cursor-pointer w-[200px] transition-shadow duration-300 ${
        isDark
          ? 'bg-blue-600 border-blue-500 text-white'
          : 'bg-blue-500 border-blue-400 text-white'
      }`}
      style={data.selected ? GLOW.blue : {}}
      title={data.description}
    >
      <Handle type="target" position={Position.Top} className="!bg-blue-400 !w-2 !h-2" />
      <div className="text-sm font-semibold text-center">{data.label}</div>
      {data.description && (
        <div className="text-[10px] text-center mt-1 text-blue-100">{data.description}</div>
      )}
      {data.expandable && (
        <div className="text-[9px] text-center mt-1 text-blue-200">[double click to expand]</div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-blue-400 !w-2 !h-2" />
    </div>
  )
}

/** 判断节点 — 菱形 */
function DecisionNode({ data }: { data: DiagramNodeData }) {
  const { isDark } = useTheme()

  return (
    <div className="relative w-[140px] h-[140px] flex items-center justify-center">
      <Handle type="target" position={Position.Top} className="!bg-amber-400 !w-2 !h-2" style={{ top: 0 }} />
      <div
        className={`absolute inset-0 rotate-45 rounded-md border-2 transition-shadow duration-300 ${
          isDark
            ? 'bg-amber-600 border-amber-500'
            : 'bg-amber-500 border-amber-400'
        }`}
        style={data.selected ? GLOW.amber : {}}
      />
      <div className="relative z-10 text-center px-2 text-white" title={data.description}>
        <div className="text-xs font-semibold leading-tight">{data.label}</div>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-amber-400 !w-2 !h-2" style={{ bottom: 0 }} />
      <Handle type="source" position={Position.Right} id="no" className="!bg-amber-400 !w-2 !h-2" style={{ right: 0 }} />
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
