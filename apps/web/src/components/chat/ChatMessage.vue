<template>
  <!-- System message -->
  <div
    v-if="message.role === 'system'"
    class="text-center text-xs text-warm-400 dark:text-warm-500 py-1"
  >
    {{ message.content }}
  </div>

  <!-- Trigger fired -->
  <div
    v-else-if="message.role === 'trigger'"
    class="flex items-center gap-2 py-1.5 px-3 rounded-lg bg-amber/6 dark:bg-amber/8 border border-amber/15 dark:border-amber/20"
  >
    <span class="w-1.5 h-1.5 rounded-full bg-amber shrink-0" />
    <span class="text-xs text-amber-shadow dark:text-amber-light">
      Triggered by <span class="font-semibold">{{ message.content }}</span>
    </span>
  </div>

  <!-- User message -->
  <div v-else-if="message.role === 'user'" class="ml-auto max-w-[80%]">
    <div
      class="card px-4 py-3 border-l-3 border-l-sapphire dark:border-l-sapphire/60"
    >
      <div class="text-xs text-warm-400 mb-1">You</div>
      <div class="text-body whitespace-pre-wrap">{{ message.content }}</div>
    </div>
  </div>

  <!-- Assistant message (parts-based: ordered text + tools) -->
  <div
    v-else-if="message.role === 'assistant' && message.parts"
    class="max-w-[90%]"
  >
    <template v-for="(part, pi) in message.parts" :key="pi">
      <!-- Text part -->
      <div v-if="part.type === 'text' && part.content" class="text-body mb-1">
        <MarkdownRenderer :content="part.content" />
      </div>
      <!-- Tool/subagent part -->
      <div v-else-if="part.type === 'tool'" class="mb-1.5">
        <ToolCallBlock
          :tc="part"
          :expanded="expandedTools[part.id]"
          @toggle="toggleTool(part.id)"
        />
      </div>
    </template>
  </div>

  <!-- Assistant message (legacy: content + tool_calls) -->
  <div v-else-if="message.role === 'assistant'" class="max-w-[90%]">
    <div v-if="message.tool_calls?.length" class="mb-2 flex flex-col gap-1.5">
      <ToolCallBlock
        v-for="tc in message.tool_calls"
        :key="tc.id"
        :tc="tc"
        :expanded="expandedTools[tc.id]"
        @toggle="toggleTool(tc.id)"
      />
    </div>
    <div v-if="message.content" class="text-body">
      <MarkdownRenderer :content="message.content" />
    </div>
  </div>

  <!-- Channel message (group chat style) -->
  <div v-else-if="message.role === 'channel'" class="max-w-[90%]">
    <div
      v-if="showSenderHeader"
      class="flex items-center gap-2 mb-1"
      :class="{ 'mt-2': !isFirst }"
    >
      <span
        class="w-5 h-5 rounded-md flex items-center justify-center text-[10px] font-bold text-white"
        :style="{ background: senderGemColor }"
      >
        {{ message.sender.charAt(0).toUpperCase() }}
      </span>
      <span class="text-xs font-semibold" :style="{ color: senderGemColor }">{{
        message.sender
      }}</span>
      <span class="text-[10px] text-warm-400">{{ message.timestamp }}</span>
    </div>
    <div class="pl-7 text-body">
      <MarkdownRenderer :content="message.content" />
    </div>
  </div>
</template>

<script setup>
import MarkdownRenderer from "@/components/common/MarkdownRenderer.vue";
import ToolCallBlock from "@/components/chat/ToolCallBlock.vue";
import { GEM } from "@/utils/colors";

const props = defineProps({
  message: { type: Object, required: true },
  prevMessage: { type: Object, default: null },
  isFirst: { type: Boolean, default: false },
});

const expandedTools = reactive({});

function toggleTool(id) {
  expandedTools[id] = !expandedTools[id];
}

const showSenderHeader = computed(() => {
  if (props.message.role !== "channel") return false;
  if (!props.prevMessage || props.prevMessage.role !== "channel") return true;
  return props.prevMessage.sender !== props.message.sender;
});

const SENDER_GEMS = [
  GEM.iolite.main,
  GEM.aquamarine.main,
  GEM.taaffeite.main,
  GEM.amber.main,
  GEM.sapphire.main,
];
const senderColorCache = {};
let nextColorIdx = 0;

const senderGemColor = computed(() => {
  const name = props.message.sender;
  if (!name) return GEM.iolite.main;
  if (!senderColorCache[name]) {
    senderColorCache[name] = SENDER_GEMS[nextColorIdx % SENDER_GEMS.length];
    nextColorIdx++;
  }
  return senderColorCache[name];
});
</script>
