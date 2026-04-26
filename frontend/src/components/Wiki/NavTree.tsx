import { useState } from 'react'
import { useWikiStore } from '../../store/useWikiStore'
import type { WikiDocument, WikiIndexNode, WikiPage } from '../../types/wiki'

export default function NavTree() {
  const wiki = useWikiStore((s) => s.wiki)
  const currentPageId = useWikiStore((s) => s.currentPageId)
  const navigateToPage = useWikiStore((s) => s.navigateToPage)

  if (!wiki) return null

  return (
    <nav className="h-full overflow-auto bg-gray-50 dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 py-3 text-sm">
      <div className="px-3 pb-2 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
        导航
      </div>
      <TreeNode
        wiki={wiki}
        pageId={wiki.index.root}
        currentPageId={currentPageId}
        onClick={navigateToPage}
        depth={0}
      />
    </nav>
  )
}

interface TreeNodeProps {
  wiki: WikiDocument
  pageId: string
  currentPageId: string | null
  onClick: (pageId: string) => void
  depth: number
}

function TreeNode({ wiki, pageId, currentPageId, onClick, depth }: TreeNodeProps) {
  const node: WikiIndexNode | undefined = wiki.index.tree[pageId]
  const page: WikiPage | undefined = wiki.pages.find((p) => p.id === pageId)
  // category 默认展开；其余叶子节点无子节点
  const [expanded, setExpanded] = useState(true)
  if (!node || !page) return null

  const hasChildren = node.children.length > 0
  const isActive = pageId === currentPageId
  const isCategory = page.type === 'category'

  // category 节点样式：分组标签，不高亮、不作为 active
  if (isCategory) {
    const indent = { paddingLeft: `${12 + depth * 14}px` }
    return (
      <div>
        <div
          style={indent}
          className="flex items-center gap-1 py-2 pr-3 cursor-pointer text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 select-none"
          onClick={() => setExpanded((v) => !v)}
          title={expanded ? '折叠' : '展开'}
        >
          <svg
            width="10"
            height="10"
            viewBox="0 0 10 10"
            className={`transition-transform ${expanded ? 'rotate-90' : ''}`}
          >
            <path d="M3 2 L7 5 L3 8" fill="none" stroke="currentColor" strokeWidth="1.5" />
          </svg>
          <span className="truncate flex-1">{node.title}</span>
        </div>
        {expanded && (
          <div>
            {node.children.map((childId) => (
              <TreeNode
                key={childId}
                wiki={wiki}
                pageId={childId}
                currentPageId={currentPageId}
                onClick={onClick}
                depth={depth + 1}
              />
            ))}
          </div>
        )}
      </div>
    )
  }

  const indent = { paddingLeft: `${12 + depth * 14}px` }

  return (
    <div>
      <div
        style={indent}
        className={`flex items-center gap-1 py-1.5 pr-3 cursor-pointer transition-colors ${
          isActive
            ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 font-medium'
            : 'hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300'
        }`}
        onClick={() => onClick(pageId)}
      >
        {hasChildren ? (
          <button
            className="w-4 h-4 flex items-center justify-center text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
            onClick={(e) => {
              e.stopPropagation()
              setExpanded((v) => !v)
            }}
            aria-label={expanded ? '折叠' : '展开'}
          >
            <svg
              width="10"
              height="10"
              viewBox="0 0 10 10"
              className={`transition-transform ${expanded ? 'rotate-90' : ''}`}
            >
              <path d="M3 2 L7 5 L3 8" fill="none" stroke="currentColor" strokeWidth="1.5" />
            </svg>
          </button>
        ) : (
          <span className="w-4 h-4 inline-block" />
        )}
        <span className="mr-1">{iconFor(page.type)}</span>
        <span className="truncate flex-1" title={page.title}>
          {page.title}
        </span>
      </div>
      {hasChildren && expanded && (
        <div>
          {node.children.map((childId) => (
            <TreeNode
              key={childId}
              wiki={wiki}
              pageId={childId}
              currentPageId={currentPageId}
              onClick={onClick}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function iconFor(type: WikiPage['type']): string {
  switch (type) {
    case 'overview':
      return '🏠'
    case 'chapter':
      return '📘'
    case 'topic':
      return '💡'
    case 'module':
      return '📦'
    case 'category':
      return ''
  }
}
