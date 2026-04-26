import { useMemo, useState } from 'react'

interface Props {
  paths: string[]
  currentFile: string | null
  onSelect: (path: string) => void
}

interface TreeNode {
  name: string
  fullPath: string
  isFile: boolean
  children: TreeNode[]
}

function buildTree(paths: string[]): TreeNode {
  const root: TreeNode = { name: '', fullPath: '', isFile: false, children: [] }
  for (const p of paths) {
    const parts = p.split('/').filter(Boolean)
    let cur = root
    let acc = ''
    parts.forEach((part, idx) => {
      acc = acc ? `${acc}/${part}` : part
      const isFile = idx === parts.length - 1
      let child = cur.children.find((c) => c.name === part && c.isFile === isFile)
      if (!child) {
        child = { name: part, fullPath: acc, isFile, children: [] }
        cur.children.push(child)
      }
      cur = child
    })
  }
  sortTree(root)
  return root
}

function sortTree(node: TreeNode) {
  node.children.sort((a, b) => {
    if (a.isFile !== b.isFile) return a.isFile ? 1 : -1
    return a.name.localeCompare(b.name)
  })
  node.children.forEach(sortTree)
}

export default function FileTree({ paths, currentFile, onSelect }: Props) {
  const [filter, setFilter] = useState('')
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set())

  const filteredPaths = useMemo(() => {
    const q = filter.trim().toLowerCase()
    if (!q) return paths
    return paths.filter((p) => p.toLowerCase().includes(q))
  }, [paths, filter])

  const tree = useMemo(() => buildTree(filteredPaths), [filteredPaths])

  // 当筛选时自动展开所有目录
  const effectiveCollapsed = filter.trim() ? new Set<string>() : collapsed

  const toggle = (path: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }

  return (
    <div className="flex flex-col h-full text-xs">
      <input
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="筛选..."
        className="m-2 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-400"
      />
      <div className="flex-1 overflow-y-auto pb-2 font-mono">
        {paths.length === 0 ? (
          <div className="px-3 py-2 text-gray-400">项目未加载</div>
        ) : tree.children.length === 0 ? (
          <div className="px-3 py-2 text-gray-400">无匹配</div>
        ) : (
          tree.children.map((child) => (
            <TreeItem
              key={child.fullPath}
              node={child}
              depth={0}
              collapsed={effectiveCollapsed}
              onToggle={toggle}
              currentFile={currentFile}
              onSelect={onSelect}
            />
          ))
        )}
      </div>
    </div>
  )
}

interface ItemProps {
  node: TreeNode
  depth: number
  collapsed: Set<string>
  onToggle: (p: string) => void
  currentFile: string | null
  onSelect: (p: string) => void
}

function TreeItem({ node, depth, collapsed, onToggle, currentFile, onSelect }: ItemProps) {
  const isCollapsed = collapsed.has(node.fullPath)
  const padding = 8 + depth * 12

  if (node.isFile) {
    const active = node.fullPath === currentFile
    return (
      <button
        onClick={() => onSelect(node.fullPath)}
        className={`w-full text-left truncate py-0.5 hover:bg-blue-50 dark:hover:bg-blue-900/30 ${
          active
            ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200'
            : 'text-gray-700 dark:text-gray-300'
        }`}
        style={{ paddingLeft: padding }}
        title={node.fullPath}
      >
        <span className="mr-1 text-gray-400">📄</span>
        {node.name}
      </button>
    )
  }

  return (
    <div>
      <button
        onClick={() => onToggle(node.fullPath)}
        className="w-full text-left py-0.5 truncate text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800"
        style={{ paddingLeft: padding }}
      >
        <span className="inline-block w-3 mr-0.5 text-gray-400">
          {isCollapsed ? '▸' : '▾'}
        </span>
        <span className="mr-1 text-gray-400">📁</span>
        {node.name}
      </button>
      {!isCollapsed &&
        node.children.map((c) => (
          <TreeItem
            key={c.fullPath}
            node={c}
            depth={depth + 1}
            collapsed={collapsed}
            onToggle={onToggle}
            currentFile={currentFile}
            onSelect={onSelect}
          />
        ))}
    </div>
  )
}
