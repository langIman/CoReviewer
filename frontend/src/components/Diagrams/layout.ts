import dagre from 'dagre'
import type { FlowData, FlowNodeType } from '../../types'

const NODE_SIZES: Record<FlowNodeType, { width: number; height: number }> = {
  start: { width: 160, height: 50 },
  end: { width: 160, height: 50 },
  process: { width: 240, height: 80 },
  decision: { width: 110, height: 110 },
}

/** dagre 自动布局，返回每个节点的 { x, y } */
export function computeLayout(data: FlowData) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 60, ranksep: 50 })

  const nodeIds = new Set<string>()
  data.nodes.forEach((n) => {
    const id = String(n.id)
    nodeIds.add(id)
    const size = NODE_SIZES[n.type] || NODE_SIZES.process
    g.setNode(id, { width: size.width, height: size.height })
  })
  data.edges.forEach((e) => {
    const src = String(e.source)
    const tgt = String(e.target)
    if (nodeIds.has(src) && nodeIds.has(tgt)) {
      g.setEdge(src, tgt)
    }
  })
  dagre.layout(g)

  const positions: Record<string, { x: number; y: number }> = {}
  data.nodes.forEach((n) => {
    const id = String(n.id)
    const pos = g.node(id)
    const size = NODE_SIZES[n.type] || NODE_SIZES.process
    positions[id] = { x: pos.x - size.width / 2, y: pos.y - size.height / 2 }
  })
  return positions
}
