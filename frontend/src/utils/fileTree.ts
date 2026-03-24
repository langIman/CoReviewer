import type { ProjectFile, FileTreeNode } from '../types'

export function buildFileTree(files: ProjectFile[]): FileTreeNode[] {
  const root: FileTreeNode[] = []

  for (const file of files) {
    const parts = file.path.split('/')
    let current = root

    for (let i = 0; i < parts.length; i++) {
      const name = parts[i]
      const isFile = i === parts.length - 1

      if (isFile) {
        current.push({ name, path: file.path, type: 'file' })
      } else {
        let dir = current.find((n) => n.type === 'directory' && n.name === name)
        if (!dir) {
          dir = { name, path: parts.slice(0, i + 1).join('/'), type: 'directory', children: [] }
          current.push(dir)
        }
        current = dir.children!
      }
    }
  }

  // 递归排序：目录在前，文件在后，各自按名称排序
  function sortNodes(nodes: FileTreeNode[]): FileTreeNode[] {
    return nodes
      .sort((a, b) => {
        if (a.type !== b.type) return a.type === 'directory' ? -1 : 1
        return a.name.localeCompare(b.name)
      })
      .map((n) =>
        n.children ? { ...n, children: sortNodes(n.children) } : n
      )
  }

  return sortNodes(root)
}
