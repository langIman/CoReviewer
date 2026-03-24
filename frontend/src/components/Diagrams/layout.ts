import dagre from 'dagre'
import type { FlowData, FlowNodeType } from '../../types'

const NODE_SIZES: Record<FlowNodeType, { width: number; height: number }> = {
  start: { width: 160, height: 50 },
  end: { width: 160, height: 50 },
  process: { width: 200, height: 80 },
  decision: { width: 140, height: 140 },
}

/** dagre 自动布局，返回每个节点的 { x, y } */
export function computeLayout(data: FlowData) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 50, ranksep: 70 })

  data.nodes.forEach((n) => {
    const size = NODE_SIZES[n.type] || NODE_SIZES.process
    g.setNode(n.id, { width: size.width, height: size.height })
  })
  data.edges.forEach((e) => g.setEdge(e.source, e.target))
  dagre.layout(g)

  const positions: Record<string, { x: number; y: number }> = {}
  data.nodes.forEach((n) => {
    const pos = g.node(n.id)
    const size = NODE_SIZES[n.type] || NODE_SIZES.process
    positions[n.id] = { x: pos.x - size.width / 2, y: pos.y - size.height / 2 }
  })
  return positions
}
