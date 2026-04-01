import { terrariumAPI, agentAPI } from "@/utils/api";
import { useMessagesStore } from "@/stores/messages";
import { useInstancesStore } from "@/stores/instances";

/**
 * Convert OpenAI-format conversation history to frontend messages.
 */
function _convertHistory(messages) {
  const result = [];
  const toolResults = {};
  for (const msg of messages) {
    if (msg.role === "tool") toolResults[msg.tool_call_id] = msg.content;
  }
  for (const msg of messages) {
    if (msg.role === "system" || msg.role === "tool") continue;
    if (msg.role === "user") {
      result.push({
        id: "h_" + result.length,
        role: "user",
        content: msg.content || "",
        timestamp: "",
      });
    } else if (msg.role === "assistant") {
      const tcs = (msg.tool_calls || []).map((tc) => ({
        id: tc.id,
        name: tc.function?.name || "unknown",
        kind: (tc.function?.name || "").startsWith("agent_")
          ? "subagent"
          : "tool",
        args: _parseArgs(tc.function?.arguments),
        status: "done",
        result: toolResults[tc.id] || "",
      }));
      result.push({
        id: "h_" + result.length,
        role: "assistant",
        content: msg.content || "",
        timestamp: "",
        tool_calls: tcs.length ? tcs : undefined,
      });
    }
  }
  return result;
}

/**
 * Replay event log to reconstruct exact live view.
 */
/**
 * Replay a single ordered event list to reconstruct chat view.
 * Every event has a `ts` timestamp. We process them strictly in order.
 * No separate message list, no interleaving heuristics.
 */
function _replayEvents(messages, events) {
  // If no events, fall back to conversation history
  if (!events?.length) return _convertHistory(messages);

  // Events are already ordered by ts from the backend
  const result = [];
  let cur = null; // current assistant message being built

  for (const evt of events) {
    if (evt.type === "user_input") {
      cur = null;
      result.push({
        id: "h_" + result.length,
        role: "user",
        content: evt.content || "",
        timestamp: "",
      });
    } else if (evt.type === "processing_start") {
      cur = {
        id: "h_" + result.length,
        role: "assistant",
        parts: [],
        timestamp: "",
      };
      result.push(cur);
    } else if (evt.type === "text") {
      if (!cur) {
        cur = {
          id: "h_" + result.length,
          role: "assistant",
          parts: [],
          timestamp: "",
        };
        result.push(cur);
      }
      const tail = cur.parts.length ? cur.parts[cur.parts.length - 1] : null;
      if (tail && tail.type === "text") {
        tail.content += evt.content;
      } else {
        cur.parts.push({ type: "text", content: evt.content });
      }
    } else if (evt.type === "activity") {
      const at = evt.activity_type;

      // Trigger fired: standalone message, breaks current assistant
      if (at === "trigger_fired") {
        cur = null;
        const channel = evt.channel || "";
        const sender = evt.sender || "";
        const label = channel ? `channel: ${channel}` : evt.name;
        const from = sender ? ` from ${sender}` : "";
        result.push({
          id: "h_" + result.length,
          role: "trigger",
          content: `${label}${from}`,
          triggerContent: evt.content || "",
          channel,
          sender,
          timestamp: "",
        });
        continue;
      }

      // Token usage: skip in replay (shown in header)
      if (at === "token_usage" || at === "processing_complete") continue;

      // Tool/subagent activity: attach to current assistant
      if (!cur) {
        cur = {
          id: "h_" + result.length,
          role: "assistant",
          parts: [],
          timestamp: "",
        };
        result.push(cur);
      }

      if (at === "tool_start" || at === "subagent_start") {
        // Finalize trailing text part
        const tail = cur.parts.length ? cur.parts[cur.parts.length - 1] : null;
        if (tail && tail.type === "text") tail._streaming = false;

        cur.parts.push({
          type: "tool",
          id: evt.id,
          name: evt.name,
          kind: at === "subagent_start" ? "subagent" : "tool",
          args: evt.args || { info: evt.detail },
          status: "done",
          result: "",
          tools_used: [],
        });
      } else if (at === "tool_done" || at === "subagent_done") {
        const tc = [...cur.parts]
          .reverse()
          .find((p) => p.type === "tool" && p.name === evt.name);
        if (tc) {
          tc.result = evt.result || evt.detail || "";
          if (evt.tools_used) tc.tools_used = evt.tools_used;
        }
      } else if (at === "tool_error" || at === "subagent_error") {
        const tc = [...cur.parts]
          .reverse()
          .find((p) => p.type === "tool" && p.name === evt.name);
        if (tc) {
          tc.status = "error";
          tc.result = evt.detail || "";
        }
      }
    } else if (evt.type === "processing_end" || evt.type === "idle") {
      cur = null;
    }
  }

  // Clean up empty parts
  for (const msg of result) {
    if (msg.parts?.length === 0) delete msg.parts;
  }
  return result;
}

function _parseArgs(args) {
  if (!args) return {};
  if (typeof args === "string") {
    try {
      return JSON.parse(args);
    } catch {
      return { raw: args };
    }
  }
  return args;
}

function wsUrl(path) {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const isDev = location.port === "5173" || location.port === "5174";
  const host = isDev ? `${location.hostname}:8001` : location.host;
  return `${protocol}//${host}${path}`;
}

export const useChatStore = defineStore("chat", {
  state: () => ({
    /** @type {Object<string, import('@/utils/api').ChatMessage[]>} */
    messagesByTab: {},
    /** @type {string | null} */
    activeTab: null,
    /** @type {string[]} */
    tabs: [],
    processing: false,
    /** @type {Object<string, {prompt: number, completion: number, total: number}>} Per-source token usage */
    tokenUsage: {},
    /** @type {string | null} */
    _instanceId: null,
    /** @type {string | null} */
    _instanceType: null,
    /** @type {WebSocket | null} Single WS for the instance */
    _ws: null,
  }),

  getters: {
    currentMessages: (state) => {
      if (!state.activeTab) return [];
      return state.messagesByTab[state.activeTab] || [];
    },
  },

  actions: {
    initForInstance(instance) {
      if (this._instanceId === instance.id) return;
      this._cleanup();
      this._instanceId = instance.id;
      this._instanceType = instance.type;
      this.tabs = [];
      this.messagesByTab = {};

      if (instance.type === "terrarium") {
        if (instance.has_root) {
          this._addTab("root");
        } else {
          this._addTab("ch:tasks");
        }
        this._connectTerrarium(instance.id);
      } else {
        const name = instance.creatures[0]?.name || instance.config_name;
        this._addTab(name);
        this._connectCreature(instance.id);
      }

      this.activeTab = this.tabs[0] || null;
    },

    openTab(tabKey) {
      this._addTab(tabKey);
      this.activeTab = tabKey;

      // Load history for creature/root tabs
      if (!tabKey.startsWith("ch:") && this._instanceType === "terrarium") {
        this._loadHistory(tabKey);
      }
    },

    _addTab(key) {
      if (!this.tabs.includes(key)) {
        this.tabs.push(key);
        this.messagesByTab[key] = [];
      }
    },

    setActiveTab(tab) {
      this.activeTab = tab;
      // Load history if tab has no messages yet (tab switch catch-up)
      if (tab && !tab.startsWith("ch:") && this._instanceType === "terrarium") {
        const msgs = this.messagesByTab[tab];
        if (msgs && msgs.length === 0) {
          this._loadHistory(tab);
        }
      }
    },

    async send(text) {
      if (!this.activeTab || !text.trim() || !this._ws) return;

      // Push user message immediately
      const tab = this.activeTab;
      this._addMsg(tab, {
        id: "u_" + Date.now(),
        role: "user",
        content: text,
        timestamp: new Date().toISOString(),
      });

      if (tab.startsWith("ch:")) {
        // Channel: send via REST
        const chName = tab.slice(3);
        try {
          await terrariumAPI.sendToChannel(
            this._instanceId,
            chName,
            text,
            "human",
          );
        } catch (err) {
          console.error("Channel send failed:", err);
        }
      } else {
        // Creature/root: send via WS
        const target = tab;
        if (this._ws.readyState === WebSocket.OPEN) {
          this._ws.send(
            JSON.stringify({ type: "input", target, message: text }),
          );
          this.processing = true;
        }
      }
    },

    async _loadHistory(target) {
      try {
        const { messages, events } = await terrariumAPI.getHistory(
          this._instanceId,
          target,
        );
        if (events?.length) {
          this.messagesByTab[target] = _replayEvents(messages, events);
          this._restoreTokenUsage(target, events);
        } else if (messages?.length) {
          this.messagesByTab[target] = _convertHistory(messages);
        }
      } catch {
        /* no history yet */
      }
    },

    /** Connect single WS for terrarium */
    _connectTerrarium(terrariumId) {
      const ws = new WebSocket(wsUrl(`/ws/terrariums/${terrariumId}`));
      ws.onmessage = (event) => this._onMessage(JSON.parse(event.data));
      ws.onclose = () => {
        this.processing = false;
      };
      this._ws = ws;

      // Load history for initial tab
      if (this.tabs[0] && !this.tabs[0].startsWith("ch:")) {
        this._loadHistory(this.tabs[0]);
      }
    },

    /** Connect single WS for standalone creature */
    _connectCreature(agentId) {
      const ws = new WebSocket(wsUrl(`/ws/creatures/${agentId}`));
      ws.onmessage = (event) => this._onMessage(JSON.parse(event.data));
      ws.onclose = () => {
        this.processing = false;
      };
      this._ws = ws;

      // Load history for the creature tab
      const tabKey = this.tabs[0];
      if (tabKey) {
        this._loadAgentHistory(agentId, tabKey);
      }
    },

    async _loadAgentHistory(agentId, tabKey) {
      try {
        const { messages, events } = await agentAPI.getHistory(agentId);
        if (events?.length) {
          this.messagesByTab[tabKey] = _replayEvents(messages, events);
          this._restoreTokenUsage(tabKey, events);
        } else if (messages?.length) {
          this.messagesByTab[tabKey] = _convertHistory(messages);
        }
      } catch {
        /* no history yet */
      }
    },

    /** Restore token usage from event log (for page refresh) */
    _restoreTokenUsage(source, events) {
      for (const evt of events) {
        if (evt.type === "activity" && evt.activity_type === "token_usage") {
          const prev = this.tokenUsage[source] || {
            prompt: 0,
            completion: 0,
            total: 0,
          };
          this.tokenUsage[source] = {
            prompt: evt.prompt_tokens || prev.prompt,
            completion: prev.completion + (evt.completion_tokens || 0),
            total: evt.total_tokens || prev.total,
          };
        }
      }
    },

    /** Handle ALL incoming WS messages */
    _onMessage(data) {
      const source = data.source || "";

      if (data.type === "text") {
        this._appendStreamChunk(source, data.content);
      } else if (data.type === "processing_start") {
        this.processing = true;
      } else if (data.type === "processing_end") {
        this._finishStream(source);
      } else if (data.type === "idle") {
        this.processing = false;
        this._finishStream(source);
      } else if (data.type === "activity") {
        this._handleActivity(source, data);
      } else if (data.type === "channel_message") {
        this._handleChannelMessage(data);
      } else if (data.type === "error") {
        this._addMsg(source, {
          id: "err_" + Date.now(),
          role: "system",
          content: "Error: " + (data.content || ""),
          timestamp: new Date().toISOString(),
        });
        this.processing = false;
      }
    },

    _handleActivity(source, data) {
      const at = data.activity_type;
      const name = data.name || "unknown";

      // Token usage: always track, even without open tab
      if (at === "token_usage") {
        const prev = this.tokenUsage[source] || {
          prompt: 0,
          completion: 0,
          total: 0,
        };
        this.tokenUsage[source] = {
          prompt: data.prompt_tokens || prev.prompt,
          completion: prev.completion + (data.completion_tokens || 0),
          total: data.total_tokens || prev.total,
        };
        return;
      }

      // Ensure we have a tab for this source (non-usage events need it)
      if (!this.messagesByTab[source]) return;
      const msgs = this.messagesByTab[source];

      // Trigger fired: show with expandable message content
      if (at === "trigger_fired") {
        const channel = data.channel || "";
        const sender = data.sender || "";
        const label = channel ? `channel: ${channel}` : name;
        const from = sender ? ` from ${sender}` : "";
        msgs.push({
          id: "trig_" + Date.now(),
          role: "trigger",
          content: `${label}${from}`,
          triggerContent: data.content || "",
          channel,
          sender,
          timestamp: new Date().toISOString(),
        });
        return;
      }

      if (at === "tool_start" || at === "subagent_start") {
        const last = this._ensureAssistantMsg(msgs);
        // Finalize any trailing text part so the tool appears AFTER it
        if (last.parts.length > 0) {
          const tail = last.parts[last.parts.length - 1];
          if (tail.type === "text") tail._streaming = false;
        }
        last.parts.push({
          type: "tool",
          id: data.id || "tc_" + Date.now(),
          name,
          kind: at === "subagent_start" ? "subagent" : "tool",
          args: data.args || { info: data.detail },
          status: "running",
          result: "",
          tools_used: data.tools_used || [],
        });
      } else if (at === "tool_done" || at === "subagent_done") {
        const last = msgs[msgs.length - 1];
        if (last?.parts) {
          const tc = [...last.parts]
            .reverse()
            .find(
              (p) =>
                p.type === "tool" && p.name === name && p.status === "running",
            );
          if (tc) {
            tc.status = "done";
            tc.result = data.result || data.detail || "";
            if (data.tools_used) tc.tools_used = data.tools_used;
          }
        }
      } else if (at === "tool_error" || at === "subagent_error") {
        const last = msgs[msgs.length - 1];
        if (last?.parts) {
          const tc = [...last.parts]
            .reverse()
            .find(
              (p) =>
                p.type === "tool" && p.name === name && p.status === "running",
            );
          if (tc) {
            tc.status = "error";
            tc.result = data.detail || "";
          }
        }
      } else if (at === "subagent_tool_start" || at === "subagent_tool_done") {
        // Sub-agent internal tool activity: attach to the running sub-agent part
        const last = msgs[msgs.length - 1];
        if (last?.parts) {
          const saName = data.subagent || data.name;
          const sa = [...last.parts]
            .reverse()
            .find(
              (p) =>
                p.type === "tool" &&
                p.kind === "subagent" &&
                p.status === "running",
            );
          if (sa) {
            if (!sa.tools_used) sa.tools_used = [];
            const toolName = data.tool || data.detail || "";
            if (
              at === "subagent_tool_start" &&
              toolName &&
              !sa.tools_used.includes(toolName)
            ) {
              sa.tools_used.push(toolName);
            }
          }
        }
      }
    },

    _handleChannelMessage(data) {
      const tabKey = `ch:${data.channel}`;

      // Update channel tab if open (skip duplicates from history replay)
      if (this.messagesByTab[tabKey]) {
        const existing = this.messagesByTab[tabKey];
        if (data.message_id && existing.some((m) => m.id === data.message_id)) {
          return; // already have this message
        }
        this.messagesByTab[tabKey].push({
          id: data.message_id || "ch_" + Date.now(),
          role: "channel",
          sender: data.sender,
          content: data.content,
          timestamp: data.timestamp,
        });
      }

      // Update shared messages store (for inspector)
      const msgStore = useMessagesStore();
      msgStore.addChannelMessage(data.channel, {
        channel: data.channel,
        sender: data.sender,
        content: data.content,
        timestamp: data.timestamp,
      });

      // Update channel counts in instance store (for topology graph)
      const instStore = useInstancesStore();
      if (instStore.current) {
        const ch = instStore.current.channels.find(
          (c) => c.name === data.channel,
        );
        if (ch) ch.message_count = (ch.message_count || 0) + 1;
      }
    },

    /** Ensure last message is an assistant with parts array */
    _ensureAssistantMsg(msgs) {
      let last = msgs[msgs.length - 1];
      if (!last || last.role !== "assistant" || !last._streaming) {
        last = {
          id: "m_" + Date.now(),
          role: "assistant",
          parts: [],
          timestamp: new Date().toISOString(),
          _streaming: true,
        };
        msgs.push(last);
      }
      if (!last.parts) last.parts = [];
      return last;
    },

    _appendStreamChunk(source, content) {
      const msgs = this.messagesByTab[source];
      if (!msgs) return;
      const last = this._ensureAssistantMsg(msgs);
      // Append to last text part if it's still streaming, otherwise create new
      const tail =
        last.parts.length > 0 ? last.parts[last.parts.length - 1] : null;
      if (tail && tail.type === "text" && tail._streaming) {
        tail.content += content;
      } else {
        last.parts.push({ type: "text", content, _streaming: true });
      }
    },

    _finishStream(source) {
      this.processing = false;
      const msgs = this.messagesByTab[source];
      if (msgs) {
        const last = msgs[msgs.length - 1];
        if (last?._streaming) {
          last._streaming = false;
          // Mark all text parts as done
          for (const p of last.parts || []) {
            if (p.type === "text") p._streaming = false;
          }
        }
      }
    },

    _addMsg(tabKey, msg) {
      if (!this.messagesByTab[tabKey]) this.messagesByTab[tabKey] = [];
      this.messagesByTab[tabKey].push(msg);
    },

    _cleanup() {
      if (this._ws) {
        this._ws.close();
        this._ws = null;
      }
    },
  },
});
