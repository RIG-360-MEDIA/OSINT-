'use client'

import { useEffect, useRef } from 'react'
import * as d3 from 'd3'

export interface ThreadNode {
  thread_id: string
  title: string
  article_count: number
  momentum: 'escalating' | 'stable' | 'fading'
  primary_entities: string[]
  last_updated_at: string
  // D3 simulation fields (mutable)
  x?: number
  y?: number
  vx?: number
  vy?: number
  fx?: number | null
  fy?: number | null
}

export interface ThreadEdge {
  source: string
  target: string
  weight: number
}

interface Props {
  nodes: ThreadNode[]
  edges: ThreadEdge[]
  onNodeClick: (node: ThreadNode) => void
  selectedNodeId: string | null
}

function nodeColor(momentum: string): string {
  if (momentum === 'escalating') return '#FEF2F2'
  if (momentum === 'fading') return '#F8FAFC'
  return '#EFF6FF'
}

function nodeStroke(momentum: string): string {
  if (momentum === 'escalating') return '#EF4444'
  if (momentum === 'fading') return '#CBD5E1'
  return '#93C5FD'
}

export default function ThreadGraph({ nodes, edges, onNodeClick, selectedNodeId }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const svg = d3.select(svgRef.current!)
    svg.selectAll('*').remove()

    if (!nodes.length || !containerRef.current) return

    const { clientWidth: width, clientHeight: height } = containerRef.current

    const radiusScale = d3
      .scaleSqrt()
      .domain([1, Math.max(d3.max(nodes, n => n.article_count) ?? 1, 10)])
      .range([12, 48])

    // Clone nodes so D3 can mutate positions
    const simNodes: ThreadNode[] = nodes.map(n => ({ ...n }))
    const nodeById = new Map(simNodes.map(n => [n.thread_id, n]))

    interface SimEdge { source: ThreadNode; target: ThreadNode; weight: number }
    const simEdges: SimEdge[] = edges
      .map(e => ({
        source: nodeById.get(e.source)!,
        target: nodeById.get(e.target)!,
        weight: e.weight,
      }))
      .filter(e => e.source && e.target)

    const simulation = d3
      .forceSimulation<ThreadNode>(simNodes)
      .force(
        'link',
        d3
          .forceLink<ThreadNode, SimEdge>(simEdges)
          .id(d => d.thread_id)
          .distance(d => 120 + (1 - d.weight) * 80)
          .strength(d => d.weight * 0.4),
      )
      .force('charge', d3.forceManyBody<ThreadNode>().strength(-250))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide<ThreadNode>().radius(d => radiusScale(d.article_count) + 14))
      .alphaDecay(0.03)

    // Zoom container
    const g = svg.append('g')
    svg.call(
      d3
        .zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.25, 3])
        .on('zoom', event => g.attr('transform', event.transform)),
    )

    // Edges (behind nodes)
    const edgeEl = g
      .append('g')
      .selectAll<SVGLineElement, SimEdge>('line')
      .data(simEdges)
      .join('line')
      .attr('stroke', '#CBD5E1')
      .attr('stroke-width', d => 1 + d.weight * 2)
      .attr('stroke-opacity', d => 0.2 + d.weight * 0.4)

    // Node groups
    const nodeG = g
      .append('g')
      .selectAll<SVGGElement, ThreadNode>('g')
      .data(simNodes)
      .join('g')
      .attr('cursor', 'pointer')
      .call(
        d3
          .drag<SVGGElement, ThreadNode>()
          .on('start', (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart()
            d.fx = d.x
            d.fy = d.y
          })
          .on('drag', (event, d) => {
            d.fx = event.x
            d.fy = event.y
          })
          .on('end', (event, d) => {
            if (!event.active) simulation.alphaTarget(0)
            d.fx = null
            d.fy = null
          }),
      )
      .on('click', (event, d) => {
        event.stopPropagation()
        onNodeClick(d)
      })

    // Circle
    nodeG
      .append('circle')
      .attr('r', d => radiusScale(d.article_count))
      .attr('fill', d => nodeColor(d.momentum))
      .attr('stroke', d => (selectedNodeId === d.thread_id ? '#F59E0B' : nodeStroke(d.momentum)))
      .attr('stroke-width', d => {
        if (selectedNodeId === d.thread_id) return 3.5
        return d.momentum === 'escalating' ? 2.5 : 1.5
      })
      .attr('stroke-dasharray', d => (d.momentum === 'fading' ? '4,3' : null))
      .attr('opacity', d => (d.momentum === 'fading' ? 0.6 : 1))
      .attr('class', d => (d.momentum === 'escalating' ? 'node-escalating' : null))

    // Article count inside node
    nodeG
      .append('text')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'central')
      .attr('fill', '#52525B')
      .attr('font-family', "'DM Mono', ui-monospace, monospace")
      .attr('font-size', d => Math.max(9, Math.min(14, radiusScale(d.article_count) * 0.38)) + 'px')
      .attr('font-weight', '600')
      .attr('pointer-events', 'none')
      .text(d => d.article_count)

    // Title label below node (only for ≥3 articles)
    nodeG
      .filter(d => d.article_count >= 3)
      .append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', d => radiusScale(d.article_count) + 14)
      .attr('fill', '#18181B')
      .attr('font-family', "'DM Sans', system-ui, sans-serif")
      .attr('font-size', '10px')
      .attr('pointer-events', 'none')
      .text(d => (d.title.length > 30 ? d.title.slice(0, 30) + '…' : d.title))

    simulation.on('tick', () => {
      edgeEl
        .attr('x1', d => (d.source as unknown as ThreadNode).x ?? 0)
        .attr('y1', d => (d.source as unknown as ThreadNode).y ?? 0)
        .attr('x2', d => (d.target as unknown as ThreadNode).x ?? 0)
        .attr('y2', d => (d.target as unknown as ThreadNode).y ?? 0)
      nodeG.attr('transform', d => `translate(${d.x ?? 0},${d.y ?? 0})`)
    })

    return () => { simulation.stop() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges])

  // Update selected node highlight without re-running full simulation
  useEffect(() => {
    if (!svgRef.current) return
    d3.select(svgRef.current)
      .selectAll<SVGCircleElement, ThreadNode>('circle')
      .attr('stroke', d => (selectedNodeId === d.thread_id ? '#F59E0B' : nodeStroke(d.momentum)))
      .attr('stroke-width', d => {
        if (selectedNodeId === d.thread_id) return 3.5
        return d.momentum === 'escalating' ? 2.5 : 1.5
      })
  }, [selectedNodeId])

  if (!nodes.length) {
    return (
      <div
        ref={containerRef}
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '12px',
        }}
      >
        <div
          style={{
            fontFamily: "'DM Mono', ui-monospace, monospace",
            fontSize: '11px',
            letterSpacing: '0.15em',
            textTransform: 'uppercase',
            color: '#A1A1AA',
          }}
        >
          THREADS FORMING
        </div>
        <div
          style={{
            fontFamily: "'DM Sans', system-ui, sans-serif",
            fontSize: '14px',
            color: '#71717A',
            textAlign: 'center',
            maxWidth: '300px',
            lineHeight: 1.6,
          }}
        >
          Story threads emerge as articles are collected and processed. Check back in a few minutes.
        </div>
      </div>
    )
  }

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%' }}>
      <svg ref={svgRef} style={{ width: '100%', height: '100%' }} />
    </div>
  )
}
