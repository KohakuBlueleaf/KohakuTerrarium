<template>
  <div class="h-full flex flex-col">
    <div
      class="flex items-center justify-between px-3 py-2 border-b border-b-warm-200 dark:border-b-warm-700 shrink-0"
    >
      <span
        class="text-xs font-medium text-warm-500 dark:text-warm-400 uppercase tracking-wider"
      >
        {{ headerText }}
      </span>
      <button
        v-if="inspector.type && inspector.type !== 'overview'"
        class="w-5 h-5 flex items-center justify-center rounded text-warm-400 hover:text-warm-600 dark:hover:text-warm-300 transition-colors"
        @click="inspector.showOverview(instance, true)"
      >
        <span class="i-carbon-close text-xs" />
      </button>
    </div>

    <div class="flex-1 overflow-y-auto p-3 text-xs">
      <!-- Overview: creatures + channels, all clickable -->
      <template v-if="!inspector.type || inspector.type === 'overview'">
        <div class="font-medium text-warm-700 dark:text-warm-300 mb-3">
          {{ instance.config_name }}
        </div>

        <div class="mb-3">
          <div
            class="text-warm-400 mb-1.5 uppercase tracking-wider text-[10px] font-medium"
          >
            Creatures
          </div>
          <div class="flex flex-col gap-1">
            <div
              v-for="c in instance.creatures"
              :key="c.name"
              class="flex items-center gap-2 px-2.5 py-1.5 rounded-lg cursor-pointer transition-colors hover:bg-warm-100 dark:hover:bg-warm-800"
              @click="openChat(c.name)"
            >
              <StatusDot :status="c.status" />
              <span class="font-medium text-warm-700 dark:text-warm-300">{{
                c.name
              }}</span>
              <span class="flex-1" />
              <span
                v-if="chat.tokenUsage[c.name]"
                class="text-[10px] text-warm-400 font-mono"
              >
                {{ formatTokens(chat.tokenUsage[c.name]?.total || 0) }}
              </span>
              <span
                class="text-[10px] px-1.5 py-0.5 rounded"
                :class="
                  c.status === 'running'
                    ? 'bg-aquamarine/10 text-aquamarine'
                    : 'bg-warm-100 dark:bg-warm-800 text-warm-400'
                "
              >
                {{ c.status }}
              </span>
            </div>
          </div>
        </div>

        <div>
          <div
            class="text-warm-400 mb-1.5 uppercase tracking-wider text-[10px] font-medium"
          >
            Channels
          </div>
          <div class="flex flex-col gap-1">
            <div
              v-for="ch in instance.channels"
              :key="ch.name"
              class="flex items-center gap-2 px-2.5 py-1.5 rounded-lg cursor-pointer transition-colors hover:bg-warm-100 dark:hover:bg-warm-800"
              @click="openChat('ch:' + ch.name)"
            >
              <span
                class="w-2 h-2 rounded-sm shrink-0"
                :class="
                  ch.type === 'broadcast' ? 'bg-taaffeite' : 'bg-aquamarine'
                "
              />
              <span class="font-medium text-warm-700 dark:text-warm-300">{{
                ch.name
              }}</span>
              <span class="flex-1" />
              <GemBadge
                v-if="ch.message_count"
                :gem="ch.type === 'broadcast' ? 'taaffeite' : 'aquamarine'"
              >
                {{ ch.message_count }}
              </GemBadge>
              <span
                class="text-[10px] px-1.5 py-0.5 rounded bg-warm-100 dark:bg-warm-800 text-warm-400"
              >
                {{ ch.type }}
              </span>
            </div>
          </div>
        </div>
      </template>

      <!-- Creature detail -->
      <template v-else-if="inspector.type === 'creature' && inspector.data">
        <div class="mb-3">
          <div class="flex items-center gap-2 mb-2">
            <StatusDot :status="inspector.data.status" />
            <span class="font-semibold text-warm-700 dark:text-warm-300">{{
              inspector.data.name
            }}</span>
            <span class="flex-1" />
            <button
              class="flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium bg-iolite/10 dark:bg-iolite/15 text-iolite dark:text-iolite-light hover:bg-iolite/20 dark:hover:bg-iolite/25 transition-colors"
              @click="openChat(inspector.data.name)"
            >
              <span class="i-carbon-chat text-xs" /> Chat
            </button>
          </div>
          <div class="flex flex-col gap-1 text-warm-500">
            <div>
              Model:
              <span class="text-warm-600 dark:text-warm-400">{{
                inspector.data.model || "default"
              }}</span>
            </div>
            <div>
              Status:
              <span class="text-warm-600 dark:text-warm-400">{{
                inspector.data.status
              }}</span>
            </div>
          </div>
        </div>

        <div
          v-if="
            inspector.data.listen_channels?.length ||
            inspector.data.send_channels?.length
          "
          class="mb-3"
        >
          <div
            class="text-warm-400 mb-1 uppercase tracking-wider text-[10px] font-medium"
          >
            Channels
          </div>
          <div
            v-if="inspector.data.listen_channels?.length"
            class="flex items-center gap-1.5 mb-1"
          >
            <span
              class="text-iolite dark:text-iolite-light text-[10px] font-semibold"
              >LISTEN</span
            >
            <span class="text-warm-600 dark:text-warm-400">{{
              inspector.data.listen_channels.join(", ")
            }}</span>
          </div>
          <div
            v-if="inspector.data.send_channels?.length"
            class="flex items-center gap-1.5"
          >
            <span class="text-aquamarine text-[10px] font-semibold">SEND</span>
            <span class="text-warm-600 dark:text-warm-400">{{
              inspector.data.send_channels.join(", ")
            }}</span>
          </div>
        </div>

        <div v-if="inspector.creatureOutputLines.length">
          <div
            class="text-warm-400 mb-1 uppercase tracking-wider text-[10px] font-medium"
          >
            Live Output
          </div>
          <div class="flex flex-col gap-0.5 font-mono text-[11px]">
            <div
              v-for="(line, i) in inspector.creatureOutputLines"
              :key="i"
              class="px-2 py-0.5 rounded"
              :class="lineClass(line.output)"
            >
              <span class="text-warm-400 mr-2">{{ line.timestamp }}</span>
              <span>{{ line.output }}</span>
            </div>
          </div>
        </div>
      </template>

      <!-- Channel detail: group chat style -->
      <template v-else-if="inspector.type === 'channel' && inspector.data">
        <div class="mb-3">
          <div class="flex items-center gap-2 mb-2">
            <span
              class="w-2.5 h-2.5 rounded-sm"
              :class="
                inspector.data.type === 'broadcast'
                  ? 'bg-taaffeite'
                  : 'bg-aquamarine'
              "
            />
            <span class="font-semibold text-warm-700 dark:text-warm-300">{{
              inspector.data.name
            }}</span>
            <GemBadge
              :gem="
                inspector.data.type === 'broadcast' ? 'taaffeite' : 'aquamarine'
              "
            >
              {{ inspector.data.type }}
            </GemBadge>
            <span class="flex-1" />
            <button
              class="flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium bg-aquamarine/10 dark:bg-aquamarine/15 text-aquamarine-shadow dark:text-aquamarine-light hover:bg-aquamarine/20 dark:hover:bg-aquamarine/25 transition-colors"
              @click="openChat('ch:' + inspector.data.name)"
            >
              <span class="i-carbon-send text-xs" /> Send
            </button>
          </div>
          <div v-if="inspector.data.description" class="text-warm-500 mb-1">
            {{ inspector.data.description }}
          </div>
          <div class="text-warm-400">
            {{ inspector.data.message_count || 0 }} messages
          </div>
        </div>

        <!-- Group chat style messages -->
        <div v-if="inspector.channelMessages?.length">
          <div
            class="text-warm-400 mb-1.5 uppercase tracking-wider text-[10px] font-medium"
          >
            Messages
          </div>
          <div class="flex flex-col gap-0.5">
            <template v-for="(msg, i) in inspector.channelMessages" :key="i">
              <!-- Show sender name when it changes -->
              <div
                v-if="
                  i === 0 ||
                  msg.sender !== inspector.channelMessages[i - 1].sender
                "
                class="flex items-center gap-1.5 mt-2 first:mt-0"
              >
                <span
                  class="w-1.5 h-1.5 rounded-full"
                  :class="senderColor(msg.sender)"
                />
                <span class="font-semibold text-warm-700 dark:text-warm-300">{{
                  msg.sender
                }}</span>
                <span class="text-warm-400 text-[10px]">{{
                  msg.timestamp
                }}</span>
              </div>
              <!-- Message content -->
              <div
                class="pl-4 py-0.5 text-warm-600 dark:text-warm-400 leading-relaxed"
              >
                {{ msg.content }}
              </div>
            </template>
          </div>
        </div>
        <div v-else class="text-warm-400 mt-2 text-center py-4">
          No messages yet.
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import StatusDot from "@/components/common/StatusDot.vue";
import GemBadge from "@/components/common/GemBadge.vue";
import { useInspectorStore } from "@/stores/inspector";
import { useChatStore } from "@/stores/chat";

const props = defineProps({
  instance: { type: Object, required: true },
});

const inspector = useInspectorStore();
const chat = useChatStore();

const headerText = computed(() => {
  if (!inspector.type || inspector.type === "overview") return "Overview";
  if (inspector.type === "creature") return inspector.selectedName;
  if (inspector.type === "channel") return inspector.selectedName;
  return "Inspector";
});

function openChat(tabKey) {
  chat.openTab(tabKey);
}

function formatTokens(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
  if (n >= 1000) return (n / 1000).toFixed(1) + "K";
  return String(n);
}

/** Assign consistent colors to different senders */
const senderColors = [
  "bg-iolite",
  "bg-aquamarine",
  "bg-taaffeite",
  "bg-amber",
  "bg-sapphire",
];
const senderColorMap = {};
let colorIdx = 0;

function senderColor(name) {
  if (!senderColorMap[name]) {
    senderColorMap[name] = senderColors[colorIdx % senderColors.length];
    colorIdx++;
  }
  return senderColorMap[name];
}

function lineClass(text) {
  if (text.startsWith("✓")) return "text-sage";
  if (text.startsWith("✗")) return "text-coral";
  if (text.startsWith("⚙")) return "text-warm-500 dark:text-warm-400";
  return "text-warm-600 dark:text-warm-300";
}
</script>
