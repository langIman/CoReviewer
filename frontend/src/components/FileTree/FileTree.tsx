import { useState } from 'react'
import { useReviewStore } from '../../store/useReviewStore'
import { buildFileTree } from '../../utils/fileTree'
import type { FileTreeNode } from '../../types'

function TreeNode({ node, depth }: { node: FileTreeNode; depth: number }) {
  const [expanded, setExpanded] = useState(true)
  const currentFile = useReviewStore((s) => s.file?.filename)
  const selectProjectFile = useReviewStore((s) => s.selectProjectFile)

  const isActive = node.type === 'file' && node.path === currentFile
  const paddingLeft = depth * 16 + 8

  if (node.type === 'directory') {
    return (
      <div>
        <div
          className="flex items-center py-1 px-2 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 text-sm text-gray-600 dark:text-gray-400"
          style={{ paddingLeft }}
          onClick={() => setExpanded(!expanded)}
        >
          <span className="mr-1 text-xs w-4 text-center">
            {expanded ? '▼' : '▶'}
          </span>
          <span className="mr-1.5">📁</span>
          <span>{node.name}</span>
        </div>
        {expanded && node.children?.map((child) => (
          <TreeNode key={child.path} node={child} depth={depth + 1} />
        ))}
      </div>
    )
  }

  return (
    <div
      className={`flex items-center py-1 px-2 cursor-pointer text-sm truncate ${
        isActive
          ? 'bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 font-medium'
          : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
      }`}
      style={{ paddingLeft }}
      onClick={() => selectProjectFile(node.path)}
      title={node.path}
    >
      <span className="mr-1.5">📄</span>
      <span className="truncate">{node.name}</span>
    </div>
  )
}

export default function FileTree() {
  const project = useReviewStore((s) => s.project)

  if (!project) return null

  const tree = buildFileTree(project.files)

  return (
    <div className="h-full flex flex-col">
      <div className="px-3 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider border-b border-gray-200 dark:border-gray-700">
        {project.project_name}
      </div>
      <div className="flex-1 overflow-auto py-1">
        {tree.map((node) => (
          <TreeNode key={node.path} node={node} depth={0} />
        ))}
      </div>
    </div>
  )
}
