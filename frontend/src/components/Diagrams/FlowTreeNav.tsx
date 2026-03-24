import { useState } from 'react'
import { useTheme } from '../../i18n/ThemeContext'
import { useLanguage } from '../../i18n/LanguageContext'
import type { FlowData, FlowNode } from '../../types'

interface FlowTreeNavProps {
  rootData: FlowData
  cache: Map<string, FlowData>
  currentPath: string[]
  focusedLabel: string | null
  onNavigate: (parentPath: string[], focusLabel?: string) => void
  onEnter: (path: string[]) => void
  expanding: Set<string>
}

function getCacheKey(node: FlowNode): string {
  return `${node.label}::${node.file || ''}::${node.line || 0}`
}

function TreeItem({
  node,
  cache,
  currentPath,
  focusedLabel,
  parentPath,
  onNavigate,
  onEnter,
  expanding,
  depth,
}: {
  node: FlowNode
  cache: Map<string, FlowData>
  currentPath: string[]
  focusedLabel: string | null
  parentPath: string[]
  onNavigate: (parentPath: string[], focusLabel?: string) => void
  onEnter: (path: string[]) => void
  expanding: Set<string>
  depth: number
}) {
  const { isDark } = useTheme()
  const [collapsed, setCollapsed] = useState(false)

  if (node.type === 'start' || node.type === 'end') return null

  const cacheKey = getCacheKey(node)
  const childData = cache.get(cacheKey)
  const hasChildren = !!childData
  const isLoading = expanding.has(cacheKey)

  const pathStr = JSON.stringify(parentPath)
  const curPathStr = JSON.stringify(currentPath)
  const isActive = pathStr === curPathStr && focusedLabel === node.label

  const childProcessNodes = hasChildren
    ? childData!.nodes.filter((n) => n.type === 'process' || n.type === 'decision')
    : []

  // 单击：始终在父层聚焦此节点
  const handleClick = () => {
    onNavigate(parentPath, node.label)
  }

  // 双击：有子图则进入
  const handleDoubleClick = () => {
    if (hasChildren) {
      onEnter([...parentPath, node.label])
    }
  }

  return (
    <div>
      <div
        className={`flex items-center gap-1 py-1 px-2 text-xs cursor-pointer rounded transition-colors ${
          isActive
            ? 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 font-medium'
            : isDark
              ? 'text-gray-400 hover:bg-gray-700 hover:text-gray-200'
              : 'text-gray-600 hover:bg-gray-100 hover:text-gray-800'
        }`}
        style={{ paddingLeft: depth * 14 + 8 }}
        onClick={handleClick}
        onDoubleClick={handleDoubleClick}
      >
        {hasChildren && childProcessNodes.length > 0 ? (
          <button
            onClick={(e) => { e.stopPropagation(); setCollapsed((v) => !v) }}
            className="w-3 text-[10px] text-center shrink-0"
          >
            {collapsed ? '▶' : '▼'}
          </button>
        ) : (
          <span className="w-3 text-center shrink-0 text-gray-300 dark:text-gray-600">
            {isLoading ? '⏳' : node.expandable ? '◇' : '·'}
          </span>
        )}
        <span className="truncate">{node.label}</span>
      </div>

      {hasChildren && !collapsed && childProcessNodes.map((child) => (
        <TreeItem
          key={child.id}
          node={child}
          cache={cache}
          currentPath={currentPath}
          focusedLabel={focusedLabel}
          parentPath={[...parentPath, node.label]}
          onNavigate={onNavigate}
          onEnter={onEnter}
          expanding={expanding}
          depth={depth + 1}
        />
      ))}
    </div>
  )
}

export default function FlowTreeNav({ rootData, cache, currentPath, focusedLabel, onNavigate, onEnter, expanding }: FlowTreeNavProps) {
  const { t } = useLanguage()
  const { isDark } = useTheme()

  const overviewPath = [t('visualize.overview')]
  const isOverviewActive = currentPath.length === 1 && !focusedLabel
  const processNodes = rootData.nodes.filter((n) => n.type === 'process' || n.type === 'decision')

  return (
    <div className={`flex flex-col h-full text-xs ${isDark ? 'bg-gray-850' : 'bg-gray-50/80'}`}>
      <div className="px-3 py-2 text-[10px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700">
        {t('visualize.directory')}
      </div>
      <div className="flex-1 overflow-auto py-1">
        <div
          className={`flex items-center gap-1 py-1 px-2 cursor-pointer rounded transition-colors mx-1 ${
            isOverviewActive
              ? 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 font-medium'
              : isDark
                ? 'text-gray-300 hover:bg-gray-700'
                : 'text-gray-700 hover:bg-gray-100'
          }`}
          onClick={() => onNavigate(overviewPath)}
        >
          <span className="w-3 text-[10px] text-center shrink-0">▼</span>
          <span>{t('visualize.overview')}</span>
        </div>

        {processNodes.map((node) => (
          <TreeItem
            key={node.id}
            node={node}
            cache={cache}
            currentPath={currentPath}
            focusedLabel={focusedLabel}
            parentPath={overviewPath}
            onNavigate={onNavigate}
            onEnter={onEnter}
            expanding={expanding}
            depth={1}
          />
        ))}
      </div>
    </div>
  )
}
