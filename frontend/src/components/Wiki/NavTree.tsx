import { useEffect, useMemo, useState } from 'react'
import { useWikiStore } from '../../store/useWikiStore'
import type { WikiDocument, WikiIndexNode, WikiPage } from '../../types/wiki'

const CN_DIGITS = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九']

function toChineseNumber(n: number): string {
  if (n <= 0) return ''
  if (n < 10) return CN_DIGITS[n]
  if (n === 10) return '十'
  if (n < 20) return '十' + CN_DIGITS[n - 10]
  if (n < 100) {
    const tens = Math.floor(n / 10)
    const ones = n % 10
    return CN_DIGITS[tens] + '十' + (ones === 0 ? '' : CN_DIGITS[ones])
  }
  return String(n)
}

function stripLeadingNumber(title: string): string {
  return title.replace(/^\s*\d+\s*[.、:：)）]\s*/, '').trim()
}

interface Heading {
  level: number
  text: string
  index: number
}

function parseHeadings(md: string | null | undefined): Heading[] {
  if (!md) return []
  const out: Heading[] = []
  let inFence = false
  for (const line of md.split('\n')) {
    if (/^\s*(```|~~~)/.test(line)) {
      inFence = !inFence
      continue
    }
    if (inFence) continue
    const m = /^(#{1,3})\s+(.+?)\s*#*\s*$/.exec(line)
    if (!m) continue
    const text = cleanInline(m[2])
    if (!text) continue
    out.push({ level: m[1].length, text, index: out.length })
  }
  return out
}

function cleanInline(s: string): string {
  return s
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .trim()
}

function scrollToHeading(index: number, retries = 30) {
  const els = document.querySelectorAll<HTMLElement>(
    '.markdown-body h1, .markdown-body h2, .markdown-body h3',
  )
  if (els.length > index) {
    els[index].scrollIntoView({ behavior: 'smooth', block: 'start' })
    return
  }
  if (retries > 0) {
    requestAnimationFrame(() => scrollToHeading(index, retries - 1))
  }
}

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
        onNavigate={navigateToPage}
        depth={0}
      />
    </nav>
  )
}

interface TreeNodeProps {
  wiki: WikiDocument
  pageId: string
  currentPageId: string | null
  onNavigate: (pageId: string) => void
  depth: number
  numberPrefix?: string
}

function TreeNode({
  wiki,
  pageId,
  currentPageId,
  onNavigate,
  depth,
  numberPrefix,
}: TreeNodeProps) {
  const node: WikiIndexNode | undefined = wiki.index.tree[pageId]
  const page: WikiPage | undefined = wiki.pages.find((p) => p.id === pageId)
  const isActive = pageId === currentPageId
  const isCategory = page?.type === 'category'

  const headings = useMemo(
    () => (page && !isCategory ? parseHeadings(page.content_md) : []),
    [page, isCategory],
  )

  const hasTreeChildren = node ? node.children.length > 0 : false
  const hasHeadings = headings.length > 0
  const expandable = hasTreeChildren || hasHeadings

  // 展开默认值：category 默认展开；leaf 仅当处于活跃态时自动展开。
  const [expanded, setExpanded] = useState(() => (isCategory ? true : isActive))
  useEffect(() => {
    if (!isCategory && isActive) setExpanded(true)
  }, [isCategory, isActive])

  if (!node || !page) return null

  // 给 chapter / module / topic 排中文序号
  const childPrefix = (childId: string, idx: number): string | undefined => {
    const child = wiki.pages.find((p) => p.id === childId)
    if (!child) return undefined
    if (
      child.type === 'module' ||
      child.type === 'topic' ||
      child.type === 'chapter'
    ) {
      return toChineseNumber(idx + 1) + '、'
    }
    return undefined
  }

  const indentPx = 10 + depth * 12

  if (isCategory) {
    return (
      <div>
        <div
          style={{ paddingLeft: `${indentPx}px` }}
          className="flex items-center gap-1 py-2 pr-3 cursor-pointer text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 select-none"
          onClick={() => setExpanded((v) => !v)}
        >
          <Chevron expanded={expanded} />
          <span className="truncate flex-1">{node.title}</span>
        </div>
        {expanded && (
          <div>
            {node.children.map((childId, idx) => (
              <TreeNode
                key={childId}
                wiki={wiki}
                pageId={childId}
                currentPageId={currentPageId}
                onNavigate={onNavigate}
                depth={depth + 1}
                numberPrefix={childPrefix(childId, idx)}
              />
            ))}
          </div>
        )}
      </div>
    )
  }

  const displayTitle = numberPrefix ? stripLeadingNumber(page.title) : page.title

  const handleHeadingClick = (idx: number) => {
    if (currentPageId !== pageId) {
      onNavigate(pageId)
      // 等新页面挂载（poll requestAnimationFrame 直到 H 元素就绪）
      requestAnimationFrame(() => scrollToHeading(idx))
    } else {
      scrollToHeading(idx)
    }
  }

  return (
    <div>
      <div
        style={{ paddingLeft: `${indentPx}px` }}
        className={`relative flex items-center gap-1 py-1.5 pr-3 cursor-pointer transition-colors ${
          isActive
            ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 font-medium'
            : 'hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300'
        }`}
        onClick={() => onNavigate(pageId)}
      >
        {isActive && (
          <span className="absolute left-0 top-0 bottom-0 w-[2px] bg-blue-500 dark:bg-blue-400" />
        )}
        {expandable ? (
          <button
            className="w-4 h-4 flex items-center justify-center text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 shrink-0"
            onClick={(e) => {
              e.stopPropagation()
              setExpanded((v) => !v)
            }}
            aria-label={expanded ? '折叠' : '展开'}
          >
            <Chevron expanded={expanded} />
          </button>
        ) : (
          <span className="w-4 h-4 inline-block shrink-0" />
        )}
        {numberPrefix && <span className="shrink-0 tabular-nums">{numberPrefix}</span>}
        <span className="truncate flex-1" title={displayTitle}>
          {displayTitle}
        </span>
      </div>

      {expanded && hasTreeChildren && (
        <div>
          {node.children.map((childId, idx) => (
            <TreeNode
              key={childId}
              wiki={wiki}
              pageId={childId}
              currentPageId={currentPageId}
              onNavigate={onNavigate}
              depth={depth + 1}
              numberPrefix={childPrefix(childId, idx)}
            />
          ))}
        </div>
      )}

      {/* 仅当该 leaf 没有自己的子页时才挂 in-page TOC，
          避免 overview 这种"既有 category 子节点又有 H1/H2"的页面把
          自己的标题甩到所有子树之后。 */}
      {expanded && hasHeadings && !hasTreeChildren && (
        <div>
          {headings.map((h) => (
            <HeadingItem
              key={h.index}
              heading={h}
              indentPx={indentPx}
              isActivePage={isActive}
              onClick={() => handleHeadingClick(h.index)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function HeadingItem({
  heading,
  indentPx,
  onClick,
}: {
  heading: Heading
  indentPx: number
  isActivePage: boolean
  onClick: () => void
}) {
  // 进一步缩进：在 leaf indent 之上加上 H 级别（H1=base, H2=+12, H3=+24）
  const headingIndent = indentPx + 16 + (heading.level - 1) * 12
  return (
    <div
      style={{ paddingLeft: `${headingIndent}px` }}
      className="flex items-center gap-1 py-1.5 pr-3 cursor-pointer transition-colors text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      title={heading.text}
    >
      <span className="truncate">{heading.text}</span>
    </div>
  )
}

function Chevron({ expanded }: { expanded: boolean }) {
  return (
    <svg
      width="10"
      height="10"
      viewBox="0 0 10 10"
      className={`transition-transform ${expanded ? 'rotate-90' : ''}`}
    >
      <path d="M3 2 L7 5 L3 8" fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}
