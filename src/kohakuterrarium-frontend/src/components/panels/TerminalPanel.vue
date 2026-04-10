<template>
  <div class="h-full w-full flex flex-col bg-black overflow-hidden">
    <!-- Header -->
    <div class="flex items-center gap-2 px-2 h-6 bg-warm-900 border-b border-warm-800 text-[10px] text-warm-400 shrink-0">
      <span class="i-carbon-terminal text-[11px]" />
      <span>Terminal</span>
      <span
        class="w-1.5 h-1.5 rounded-full"
        :class="connected ? 'bg-aquamarine' : 'bg-warm-600'"
      />
      <span class="flex-1" />
      <button
        v-if="!connected"
        class="px-1.5 py-0.5 rounded text-warm-500 hover:text-warm-300 hover:bg-warm-800"
        @click="connect"
      >
        Connect
      </button>
    </div>
    <!-- Terminal container -->
    <div ref="termEl" class="flex-1 min-h-0" />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { Terminal } from "xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebLinksAddon } from "@xterm/addon-web-links";
import "xterm/css/xterm.css";

import { useInstancesStore } from "@/stores/instances";

const props = defineProps({
  instance: { type: Object, default: null },
});

const instances = useInstancesStore();
const termEl = ref(null);
const connected = ref(false);

let term = null;
let fitAddon = null;
let ws = null;
let resizeObserver = null;

const agentId = computed(() => props.instance?.id || instances.current?.id || null);

function wsUrl(path) {
  if (typeof window === "undefined") return path;
  const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${window.location.host}${path}`;
}

function connect() {
  if (!agentId.value || ws) return;
  ws = new WebSocket(wsUrl(`/ws/terminal/${agentId.value}`));

  ws.onopen = () => {
    connected.value = true;
    // Send initial resize.
    if (term) {
      ws.send(JSON.stringify({
        type: "resize",
        rows: term.rows,
        cols: term.cols,
      }));
    }
  };

  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === "output" && term) {
        term.write(msg.data);
      } else if (msg.type === "error" && term) {
        term.write("\r\n\x1b[31m" + msg.data + "\x1b[0m\r\n");
      }
    } catch {
      // ignore
    }
  };

  ws.onclose = () => {
    connected.value = false;
    ws = null;
    if (term) term.write("\r\n\x1b[33m[disconnected]\x1b[0m\r\n");
  };

  ws.onerror = () => {
    connected.value = false;
  };
}

function disconnect() {
  if (ws) {
    try { ws.close(); } catch { /* ignore */ }
    ws = null;
  }
  connected.value = false;
}

onMounted(() => {
  term = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: "CaskaydiaCove NF, CaskaydiaCove Nerd Font, JetBrainsMono NF, FiraCode NF, Hack NF, JetBrains Mono, Fira Code, monospace",
    theme: {
      background: "#1a1a2e",
      foreground: "#e0e0e0",
      cursor: "#e0e0e0",
      selectionBackground: "#44475a",
    },
  });

  fitAddon = new FitAddon();
  term.loadAddon(fitAddon);
  term.loadAddon(new WebLinksAddon());

  if (termEl.value) {
    term.open(termEl.value);
    fitAddon.fit();
  }

  // Forward keystrokes to WS.
  term.onData((data) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "input", data }));
    }
  });

  // Handle resize.
  term.onResize(({ rows, cols }) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "resize", rows, cols }));
    }
  });

  // Watch container resize to refit.
  if (termEl.value && typeof ResizeObserver !== "undefined") {
    resizeObserver = new ResizeObserver(() => {
      fitAddon?.fit();
    });
    resizeObserver.observe(termEl.value);
  }

  // Auto-connect if we have an agent.
  if (agentId.value) connect();
});

watch(agentId, (id, prev) => {
  if (prev) disconnect();
  if (id) connect();
});

onUnmounted(() => {
  disconnect();
  if (resizeObserver) {
    resizeObserver.disconnect();
    resizeObserver = null;
  }
  if (term) {
    term.dispose();
    term = null;
  }
});
</script>
