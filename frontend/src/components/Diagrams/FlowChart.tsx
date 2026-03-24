import { useCallback, useMemo, useRef, useState, useEffect } from 'react'
import {
  ReactFlow,
  Background,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  MarkerType,
  type Node,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { FlowData } from '../../types'
import { useReviewStore } from '../../store/useReviewStore'
import { useTheme } from '../../i18n/ThemeContext'
import { useLanguage } from '../../i18n/LanguageContext'
import { visualizeDetail } from '../../services/api'
import { computeLayout } from './layout'
import CustomNode from './CustomNode'
import FlowTreeNav from './FlowTreeNav'

const nodeTypes = { custom: CustomNode }

export default function FlowChart({ data }: { data: FlowData }) {
  return (
    <ReactFlowProvider>
      <FlowChartInner data={data} />
    </ReactFlowProvider>
  )
}

function FlowChartInner({ data: rootData }: { data: FlowData }) {
  const { isDark } = useTheme()
  const { t } = useLanguage()
  const { fitView, zoomIn, zoomOut, setCenter, getNode } = useReactFlow()
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const selectProjectFile = useReviewStore((s) => s.selectProjectFile)
  const setHighlightLines = useReviewStore((s) => s.setHighlightLines)

  // 当前显示的 FlowData（直接存引用，不通过路径解析）
  const [currentData, setCurrentData] = useState<FlowData>(rootData)
  const [navPath, setNavPath] = useState<string[]>([t('visualize.overview')])
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [focusedLabel, setFocusedLabel] = useState<string | null>(null)
  const [expanding, setExpanding] = useState<Set<string>>(new Set())
  const cacheRef = useRef<Map<string, FlowData>>(new Map())
  const [cacheVersion, setCacheVersion] = useState(0)

  // 根据路径解析 FlowData（纯函数，不用 useCallback）
  const resolveData = (path: string[]): FlowData | null => {
    if (path.length <= 1) return rootData
    let data: FlowData = rootData
    for (let i = 1; i < path.length; i++) {
      const node = data.nodes.find((n) => n.label === path[i])
      if (!node) return null
      const cacheKey = `${node.label}::${node.file || ''}::${node.line || 0}`
      const cached = cacheRef.current.get(cacheKey)
      if (!cached) return null
      data = cached
    }
    return data
  }

  // 导航到某个路径
  const navigateTo = useCallback((path: string[], data: FlowData) => {
    setNavPath(path)
    setCurrentData(data)
    setSelectedNodeId(null)
    setFocusedLabel(null)
  }, [])

  // 构建节点
  const buildNodes = (flowData: FlowData, selId: string | null): Node[] => {
    const pos = computeLayout(flowData)
    return flowData.nodes.map((n) => ({
      id: n.id,
      type: 'custom',
      position: pos[n.id] || { x: 0, y: 0 },
      data: {
        nodeType: n.type,
        label: n.label,
        description: n.description,
        file: n.file,
        line: n.line,
        expandable: n.expandable,
        selected: n.id === selId,
      },
    }))
  }

  const buildEdges = (flowData: FlowData): Edge[] =>
    flowData.edges.map((e, i) => ({
      id: `${e.source}-${e.target}-${i}`,
      source: e.source,
      target: e.target,
      label: e.label || '',
      animated: false,
      markerEnd: { type: MarkerType.ArrowClosed, width: 15, height: 15 },
      style: { stroke: isDark ? '#60a5fa' : '#3b82f6', strokeWidth: 1.5 },
      labelStyle: { fontSize: 10, fill: isDark ? '#93c5fd' : '#3b82f6' },
    }))

  const [nodes, setNodes] = useNodesState(buildNodes(currentData, null))
  const [edges, setEdges] = useEdgesState(buildEdges(currentData))

  // currentData 变化时重新渲染图
  const prevDataRef = useRef<FlowData>(currentData)
  useEffect(() => {
    if (prevDataRef.current !== currentData) {
      prevDataRef.current = currentData
      setNodes(buildNodes(currentData, null))
      setEdges(buildEdges(currentData))
      setTimeout(() => fitView({ padding: 0.3 }), 50)
    }
  }, [currentData]) // eslint-disable-line react-hooks/exhaustive-deps

  // 选中节点高亮
  const selectNode = useCallback(
    (nodeId: string | null) => {
      setSelectedNodeId(nodeId)
      setNodes((nds) =>
        nds.map((n) => ({
          ...n,
          data: { ...n.data, selected: n.id === nodeId },
        }))
      )
    },
    [setNodes]
  )

  // 聚焦到某个节点
  const focusNode = useCallback(
    (nodeId: string) => {
      setTimeout(() => {
        const node = getNode(nodeId)
        if (node) {
          setCenter(node.position.x + 100, node.position.y + 40, { zoom: 1.2, duration: 400 })
        }
      }, 100)
    },
    [getNode, setCenter]
  )

  // 单击/双击区分：延迟单击，双击时取消
  const clickTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      // 先立即高亮（视觉反馈不延迟）
      selectNode(node.id)
      setFocusedLabel((node.data as { label: string }).label)

      // 延迟执行代码跳转，给双击机会取消
      if (clickTimerRef.current) clearTimeout(clickTimerRef.current)
      clickTimerRef.current = setTimeout(() => {
        clickTimerRef.current = null
        const { file, line } = node.data as { file?: string; line?: number }
        if (file && line) {
          selectProjectFile(file)
          setTimeout(() => setHighlightLines({ start: line, end: line }), 100)
        }
      }, 250)
    },
    [selectNode, selectProjectFile, setHighlightLines]
  )

  const handlePaneClick = useCallback(() => {
    selectNode(null)
    setFocusedLabel(null)
  }, [selectNode])

  // 双击展开节点
  const handleNodeDoubleClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      // 取消单击的延迟动作
      if (clickTimerRef.current) {
        clearTimeout(clickTimerRef.current)
        clickTimerRef.current = null
      }

      const d = node.data as { expandable?: boolean; label: string; description: string; file?: string; line?: number }
      if (!d.expandable) return

      const cacheKey = `${d.label}::${d.file || ''}::${d.line || 0}`

      const cached = cacheRef.current.get(cacheKey)
      if (cached) {
        setNavPath((prev) => [...prev, d.label])
        setCurrentData(cached)
        setSelectedNodeId(null)
        setFocusedLabel(null)
        return
      }

      if (expanding.has(cacheKey)) return
      setExpanding((prev) => new Set([...prev, cacheKey]))

      visualizeDetail({
        label: d.label,
        description: d.description,
        file: d.file,
        line: d.line,
      })
        .then((subData) => {
          cacheRef.current.set(cacheKey, subData)
          setCacheVersion((v) => v + 1)
          setNavPath((prev) => [...prev, d.label])
          setCurrentData(subData)
          setSelectedNodeId(null)
          setFocusedLabel(null)
        })
        .catch(() => {})
        .finally(() => {
          setExpanding((prev) => {
            const next = new Set(prev)
            next.delete(cacheKey)
            return next
          })
        })
    },
    [expanding]
  )

  // 树形目录：单击聚焦
  const handleTreeNavigate = useCallback(
    (path: string[], focusLabel?: string) => {
      const data = resolveData(path)
      if (!data) return

      setNavPath(path)
      setCurrentData(data)

      if (focusLabel) {
        const targetNode = data.nodes.find((n) => n.label === focusLabel)
        if (targetNode) {
          // 先渲染图，再选中聚焦
          setTimeout(() => {
            selectNode(targetNode.id)
            setFocusedLabel(focusLabel)
            focusNode(targetNode.id)
          }, 150)
        }
      } else {
        selectNode(null)
        setFocusedLabel(null)
      }
    },
    [selectNode, focusNode] // eslint-disable-line react-hooks/exhaustive-deps
  )

  // 树形目录：双击进入
  const handleTreeEnter = useCallback(
    (path: string[]) => {
      const data = resolveData(path)
      if (!data) return
      setNavPath(path)
      setCurrentData(data)
      setSelectedNodeId(null)
      setFocusedLabel(null)
    },
    [] // eslint-disable-line react-hooks/exhaustive-deps
  )

  const toggleFullscreen = useCallback(() => {
    setIsFullscreen((v) => !v)
    setTimeout(() => fitView({ padding: 0.3 }), 50)
  }, [fitView])

  const wrapperClass = isFullscreen
    ? 'fixed inset-0 z-50 bg-white dark:bg-gray-900 flex flex-col'
    : 'border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden shadow-sm bg-white dark:bg-gray-800'

  return (
    <div className={wrapperClass}>
      {/* 顶栏 */}
      <div className="flex items-center gap-2 px-4 py-2.5 bg-gray-50/80 dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700">
        <span className="text-xs font-semibold px-2.5 py-1 rounded-md border text-purple-700 dark:text-purple-300 bg-purple-50 dark:bg-purple-900/40 border-purple-200 dark:border-purple-700">
          {t('response.visualize')}
        </span>

        <div className="flex items-center gap-1 text-xs text-gray-400">
          {navPath.map((label, i) => (
            <span key={i} className="flex items-center gap-1">
              {i > 0 && <span className="text-gray-300 dark:text-gray-600">/</span>}
              <button
                onClick={() => {
                  const path = navPath.slice(0, i + 1)
                  const data = resolveData(path)
                  if (data) navigateTo(path, data)
                }}
                className={`hover:text-blue-500 transition-colors ${
                  i === navPath.length - 1 ? 'text-gray-600 dark:text-gray-300 font-medium' : ''
                }`}
              >
                {label}
              </button>
            </span>
          ))}
        </div>

        {expanding.size > 0 && (
          <span className="text-xs text-amber-600 dark:text-amber-400 animate-pulse">
            {t('visualize.expanding')} ({expanding.size})
          </span>
        )}

        <div className="ml-auto flex items-center gap-1">
          <button onClick={() => zoomIn()} className="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-500 dark:text-gray-400" title="Zoom in">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          </button>
          <button onClick={() => zoomOut()} className="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-500 dark:text-gray-400" title="Zoom out">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="5" y1="12" x2="19" y2="12"/></svg>
          </button>
          <button onClick={() => fitView({ padding: 0.3 })} className="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-500 dark:text-gray-400" title="Fit view">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>
            </svg>
          </button>
          <button onClick={toggleFullscreen} className="p-1.5 rounded hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-500 dark:text-gray-400" title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}>
            {isFullscreen ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" y1="10" x2="21" y2="3"/><line x1="3" y1="21" x2="10" y2="14"/>
              </svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/>
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* 内容区 */}
      <div className={`flex ${isFullscreen ? 'flex-1' : ''}`} style={isFullscreen ? {} : { height: 500 }}>
        {/* 目录侧栏 */}
        <div className={`flex-shrink-0 border-r border-gray-200 dark:border-gray-700 overflow-auto transition-all duration-200 ${sidebarOpen ? 'w-48' : 'w-0 overflow-hidden border-r-0'}`}>
          <FlowTreeNav
            rootData={rootData}
            cache={cacheRef.current}
            currentPath={navPath}
            focusedLabel={focusedLabel}
            onNavigate={handleTreeNavigate}
            onEnter={handleTreeEnter}
            expanding={expanding}
          />
        </div>
        {/* 收起/展开箭头 */}
        <button
          onClick={() => setSidebarOpen((v) => !v)}
          className="flex-shrink-0 w-4 flex items-center justify-center hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-400 dark:text-gray-500 transition-colors"
          title={sidebarOpen ? 'Collapse' : 'Expand'}
        >
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            {sidebarOpen
              ? <polyline points="6 2 3 5 6 8" />
              : <polyline points="4 2 7 5 4 8" />
            }
          </svg>
        </button>

        <div className="flex-1">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodeClick={handleNodeClick}
            onNodeDoubleClick={handleNodeDoubleClick}
            onPaneClick={handlePaneClick}
            fitView
            fitViewOptions={{ padding: 0.3, minZoom: 0.3 }}
            minZoom={0.15}
            proOptions={{ hideAttribution: true }}
            colorMode={isDark ? 'dark' : 'light'}
          >
            <Background color={isDark ? '#374151' : '#e5e7eb'} gap={20} />
          </ReactFlow>
        </div>
      </div>
    </div>
  )
}
