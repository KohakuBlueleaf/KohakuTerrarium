<template>
  <div class="h-full w-full topology-graph">
    <VueFlow
      :nodes="flowNodes"
      :edges="flowEdges"
      :fit-view-on-init="true"
      :nodes-draggable="true"
      :nodes-connectable="false"
      :zoom-on-scroll="true"
      :pan-on-drag="true"
      :prevent-scrolling="true"
      :min-zoom="0.3"
      :max-zoom="2"
      @node-click="onNodeClick"
      @edge-click="onEdgeClick"
    >
      <template #node-creature="{ data }">
        <CreatureNode :data="data" />
      </template>
      <template #node-hub="{ data }">
        <HubChannelNode :data="data" />
      </template>
      <template #node-leaf="{ data }">
        <LeafChannelNode :data="data" />
      </template>
    </VueFlow>
  </div>
</template>

<script setup>
import { VueFlow, useVueFlow, MarkerType } from "@vue-flow/core";
import dagre from "dagre";
import CreatureNode from "./CreatureNode.vue";
import HubChannelNode from "./HubChannelNode.vue";
import LeafChannelNode from "./LeafChannelNode.vue";
import { GEM } from "@/utils/colors";

const props = defineProps({
  instance: { type: Object, required: true },
});

const emit = defineEmits(["node-click"]);

const { fitView } = useVueFlow({ id: "topology" });

function analyzeTopology(instance) {
  const channels = {};
  for (const ch of instance.channels) {
    channels[ch.name] = { senders: [], listeners: [], channel: ch };
  }
  for (const c of instance.creatures) {
    for (const ch of c.send_channels || []) {
      if (channels[ch]) channels[ch].senders.push(c.name);
    }
    for (const ch of c.listen_channels || []) {
      if (channels[ch]) channels[ch].listeners.push(c.name);
    }
  }
  return channels;
}

const graphData = computed(() => {
  const inst = props.instance;
  if (!inst?.creatures?.length) return { nodes: [], edges: [] };

  const topology = analyzeTopology(inst);
  const nodes = [];
  const edges = [];
  const creatureNames = new Set(inst.creatures.map((c) => c.name));

  // Creature nodes
  for (const c of inst.creatures) {
    nodes.push({
      id: `c-${c.name}`,
      type: "creature",
      data: { name: c.name, status: c.status, raw: c },
      position: { x: 0, y: 0 },
    });
  }

  for (const [chName, info] of Object.entries(topology)) {
    // Skip direct creature channels
    if (
      creatureNames.has(chName) &&
      info.listeners.length <= 1 &&
      info.senders.length === 0
    ) {
      continue;
    }

    const { senders, listeners, channel } = info;
    const totalConnections = new Set([...senders, ...listeners]).size;
    if (totalConnections === 0) continue;

    // Input-only (external source -> creatures)
    if (senders.length === 0 && listeners.length > 0) {
      nodes.push({
        id: `leaf-${chName}`,
        type: "leaf",
        data: {
          name: chName,
          channelType: channel.type,
          messageCount: channel.message_count ?? 0,
          handleSide: "right",
          raw: channel,
        },
        position: { x: 0, y: 0 },
      });
      for (const l of listeners) {
        edges.push({
          id: `leaf-${chName}-${l}`,
          source: `leaf-${chName}`,
          target: `c-${l}`,
          targetHandle: "left",
          style: { stroke: GEM.iolite.main, strokeWidth: 1.5 },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: GEM.iolite.main,
            width: 12,
            height: 12,
          },
          data: { channelName: chName, raw: channel },
        });
      }
      continue;
    }

    // Output-only (creatures -> external sink)
    if (senders.length > 0 && listeners.length === 0) {
      nodes.push({
        id: `leaf-${chName}`,
        type: "leaf",
        data: {
          name: chName,
          channelType: channel.type,
          messageCount: channel.message_count ?? 0,
          handleSide: "left",
          raw: channel,
        },
        position: { x: 0, y: 0 },
      });
      for (const s of senders) {
        edges.push({
          id: `${s}-leaf-${chName}`,
          source: `c-${s}`,
          sourceHandle: "right",
          target: `leaf-${chName}`,
          style: { stroke: GEM.aquamarine.main, strokeWidth: 1.5 },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: GEM.aquamarine.main,
            width: 12,
            height: 12,
          },
          data: { channelName: chName, raw: channel },
        });
      }
      continue;
    }

    // 1:1: direct labeled edge, no channel node
    if (
      senders.length === 1 &&
      listeners.length === 1 &&
      senders[0] !== listeners[0]
    ) {
      edges.push({
        id: `direct-${chName}`,
        source: `c-${senders[0]}`,
        sourceHandle: "right",
        target: `c-${listeners[0]}`,
        targetHandle: "left",
        label: chName,
        labelStyle: {
          fontSize: "10px",
          fontWeight: "600",
          fill: "var(--color-text-muted)",
        },
        labelBgStyle: { fill: "var(--color-bg)", fillOpacity: 0.8 },
        labelBgPadding: [4, 6],
        labelBgBorderRadius: 4,
        style: { stroke: GEM.aquamarine.main, strokeWidth: 1.5 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: GEM.aquamarine.main,
          width: 12,
          height: 12,
        },
        data: { channelName: chName, raw: channel },
      });
      continue;
    }

    // Hub node for N:1 / 1:N / N:N
    nodes.push({
      id: `hub-${chName}`,
      type: "hub",
      data: {
        name: chName,
        channelType: channel.type,
        messageCount: channel.message_count ?? 0,
        raw: channel,
      },
      position: { x: 0, y: 0 },
    });

    // Hub edges use creature top/bottom handles, hub top/bottom handles
    const processed = new Set();
    for (const s of senders) {
      const alsoListens = listeners.includes(s);
      if (alsoListens) {
        // Bidirectional
        edges.push({
          id: `${s}-${chName}-bidi`,
          source: `c-${s}`,
          sourceHandle: "bottom",
          target: `hub-${chName}`,
          targetHandle: "top",
          style: { stroke: GEM.taaffeite.main, strokeWidth: 2 },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: GEM.taaffeite.main,
            width: 10,
            height: 10,
          },
          markerStart: {
            type: MarkerType.ArrowClosed,
            color: GEM.taaffeite.main,
            width: 10,
            height: 10,
          },
          data: { channelName: chName, raw: channel },
        });
        processed.add(s);
      } else {
        // Send only
        edges.push({
          id: `${s}-${chName}-send`,
          source: `c-${s}`,
          sourceHandle: "bottom",
          target: `hub-${chName}`,
          targetHandle: "top",
          style: { stroke: GEM.aquamarine.main, strokeWidth: 1.5 },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: GEM.aquamarine.main,
            width: 12,
            height: 12,
          },
          data: { channelName: chName, raw: channel },
        });
      }
    }
    for (const l of listeners) {
      if (processed.has(l)) continue;
      edges.push({
        id: `${chName}-${l}-listen`,
        source: `hub-${chName}`,
        sourceHandle: "bottom",
        target: `c-${l}`,
        targetHandle: "top",
        style: { stroke: GEM.iolite.main, strokeWidth: 1.5 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: GEM.iolite.main,
          width: 12,
          height: 12,
        },
        data: { channelName: chName, raw: channel },
      });
    }
  }

  // Dagre layout
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: "LR",
    nodesep: 50,
    ranksep: 100,
    marginx: 30,
    marginy: 30,
  });

  const nodeSize = (type) => {
    if (type === "creature") return { w: 140, h: 52 };
    if (type === "leaf") return { w: 90, h: 30 };
    return { w: 100, h: 36 };
  };

  for (const node of nodes) {
    const { w, h } = nodeSize(node.type);
    g.setNode(node.id, { width: w, height: h });
  }
  for (const edge of edges) {
    g.setEdge(edge.source, edge.target);
  }
  dagre.layout(g);

  const laid = nodes.map((node) => {
    const pos = g.node(node.id);
    const { w, h } = nodeSize(node.type);
    return { ...node, position: { x: pos.x - w / 2, y: pos.y - h / 2 } };
  });

  return { nodes: laid, edges };
});

const flowNodes = computed(() => graphData.value.nodes);
const flowEdges = computed(() => graphData.value.edges);

watch(
  () => props.instance,
  async () => {
    await nextTick();
    setTimeout(() => fitView({ padding: 0.2, duration: 300 }), 80);
  },
  { deep: true },
);

function onNodeClick(event) {
  // VueFlow may pass (MouseEvent, Node) or { event, node }
  const node = event.node || event;
  if (!node?.type) return;
  if (node.type === "creature") {
    emit("node-click", { type: "creature", data: node.data.raw });
  } else if (node.type === "hub" || node.type === "leaf") {
    emit("node-click", { type: "channel", data: node.data.raw });
  }
}

function onEdgeClick(event) {
  const edge = event.edge || event;
  if (edge?.data?.raw) {
    emit("node-click", { type: "channel", data: edge.data.raw });
  }
}
</script>

<style>
.topology-graph .vue-flow {
  background: transparent !important;
}
.topology-graph .vue-flow__node {
  background: none !important;
  border: none !important;
  border-radius: 0 !important;
  padding: 0 !important;
  box-shadow: none !important;
}
.topology-graph .vue-flow__node:focus {
  outline: none !important;
}
.topology-graph .vue-flow__node.selected {
  box-shadow: none !important;
}
.topology-graph .vue-flow__edge-path {
  stroke-linecap: round;
}
.topology-graph .vue-flow__background,
.topology-graph .vue-flow__minimap,
.topology-graph .vue-flow__controls {
  display: none;
}
.topology-graph .vue-flow__edge-text {
  pointer-events: all;
  cursor: pointer;
}
</style>
