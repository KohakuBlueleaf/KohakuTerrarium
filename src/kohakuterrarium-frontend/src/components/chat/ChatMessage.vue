<template>
  <!-- System message -->
  <div v-if="message.role === 'system'" class="text-center text-xs text-warm-400 dark:text-warm-500 py-1">
    {{ message.content }}
  </div>

  <!-- Context cleared banner -->
  <div v-else-if="message.role === 'clear'" class="flex items-center gap-3 py-2">
    <div class="flex-1 border-t border-warm-300 dark:border-warm-600 border-dashed" />
    <span class="text-xs text-warm-400 dark:text-warm-500 shrink-0"> Context Cleared{{ message.messagesCleared ? ` — ${message.messagesCleared} messages` : "" }} </span>
    <div class="flex-1 border-t border-warm-300 dark:border-warm-600 border-dashed" />
  </div>

  <!-- Context compacted (accordion) -->
  <div v-else-if="message.role === 'compact'" class="rounded-lg overflow-hidden" :class="message.status === 'running' ? 'bg-amber/6 dark:bg-amber/8 border border-amber/15 dark:border-amber/20' : 'bg-iolite/6 dark:bg-iolite/8 border border-iolite/15 dark:border-iolite/20'">
    <div role="button" tabindex="0" class="flex items-center gap-2 py-1.5 px-3 cursor-pointer select-none" @click="toggleTool('compact_' + message.id)" @keydown.enter="toggleTool('compact_' + message.id)" @keydown.space.prevent="toggleTool('compact_' + message.id)">
      <span v-if="message.status === 'running'" class="w-1.5 h-1.5 rounded-full bg-amber kohaku-pulse shrink-0" />
      <span class="text-xs font-medium" :class="message.status === 'running' ? 'text-amber dark:text-amber-light' : 'text-iolite dark:text-iolite-light'">
        {{ message.status === "running" ? "Compacting context..." : `Context Compacted (round ${message.round || "?"})` }}
      </span>
      <span v-if="message.messagesCompacted" class="text-[10px] text-warm-400"> {{ message.messagesCompacted }} messages summarized </span>
      <span class="flex-1" />
      <span v-if="message.summary" class="i-carbon-chevron-down text-warm-400 text-[10px] transition-transform" :class="{ 'rotate-180': expandedTools['compact_' + message.id] }" />
    </div>
    <div v-if="expandedTools['compact_' + message.id] && message.summary" class="px-3 py-2 border-t border-iolite/10 dark:border-iolite/15 text-xs max-h-48 overflow-y-auto">
      <MarkdownRenderer :content="message.summary" />
    </div>
  </div>

  <!-- Processing error -->
  <div v-else-if="message.role === 'error'" class="rounded-lg bg-coral/8 dark:bg-coral/12 border border-coral/25 dark:border-coral/30 overflow-hidden">
    <div role="button" tabindex="0" class="flex items-center gap-2 py-2 px-3 cursor-pointer select-none hover:bg-coral/12 dark:hover:bg-coral/18" @click="errorExpanded = !errorExpanded" @keydown.enter="errorExpanded = !errorExpanded" @keydown.space.prevent="errorExpanded = !errorExpanded">
      <span class="text-coral font-bold text-sm">&#x2717;</span>
      <span class="text-coral dark:text-coral-light font-semibold text-xs flex-1">
        {{ message.errorType || "Processing Error" }}
      </span>
      <span v-if="errorFirstLine" class="text-xs text-coral-shadow dark:text-coral-light/70 font-mono truncate max-w-[60%]">
        {{ errorFirstLine }}
      </span>
      <span class="i-carbon-chevron-down text-coral/60 transition-transform text-[10px]" :class="{ 'rotate-180': errorExpanded }" />
    </div>
    <div v-if="errorExpanded" class="px-3 pb-2 text-xs text-coral-shadow dark:text-coral-light/80 font-mono whitespace-pre-wrap border-t border-coral/20">
      {{ message.content }}
    </div>
  </div>

  <!-- Trigger fired (expandable if has message content) -->
  <div v-else-if="message.role === 'trigger'" class="rounded-lg bg-amber/6 dark:bg-amber/8 border border-amber/15 dark:border-amber/20 overflow-hidden">
    <div :role="message.triggerContent ? 'button' : undefined" :tabindex="message.triggerContent ? 0 : undefined" class="flex items-center gap-2 py-1.5 px-3" :class="message.triggerContent ? 'cursor-pointer select-none' : ''" @click="message.triggerContent && toggleTool('trig_' + message.id)" @keydown.enter="message.triggerContent && toggleTool('trig_' + message.id)" @keydown.space.prevent="message.triggerContent && toggleTool('trig_' + message.id)">
      <span class="w-1.5 h-1.5 rounded-full bg-amber shrink-0" />
      <span class="text-xs text-amber-shadow dark:text-amber-light flex-1">
        Triggered by <span class="font-semibold">{{ message.content }}</span>
      </span>
      <span v-if="message.triggerContent" class="i-carbon-chevron-down text-amber/50 text-[10px] transition-transform" :class="{ 'rotate-180': expandedTools['trig_' + message.id] }" />
    </div>
    <div v-if="expandedTools['trig_' + message.id] && message.triggerContent" class="px-3 py-2 border-t border-amber/10 dark:border-amber/15 text-xs max-h-32 overflow-y-auto">
      <MarkdownRenderer :content="message.triggerContent" />
    </div>
  </div>

  <!-- User message -->
  <div v-else-if="message.role === 'user'" class="ml-auto max-w-[80%] group relative">
    <div class="card px-4 py-3 border-l-3 flex flex-col items-end" :class="message.queued ? 'border-l-amber dark:border-l-amber/60 opacity-70' : 'border-l-sapphire dark:border-l-sapphire/60'">
      <div class="text-xs text-warm-400 mb-1 flex items-center justify-end gap-1.5 w-full">
        <span>You</span>
        <span v-if="message.queued" class="px-1.5 py-0.5 rounded text-[9px] font-medium bg-amber/15 text-amber leading-none">Queued</span>
      </div>
      <div class="flex flex-col gap-2 w-full">
        <div v-if="message.attachments?.length" class="flex flex-wrap gap-2 mb-1 justify-end">
          <a v-for="file in message.attachments" :key="file.id || file.url || file.name" :href="file.url" target="_blank" rel="noreferrer" class="attachment-chip" :class="{ 'attachment-chip-image': file.type === 'image' && file.url }" @click="onAttachmentClick($event, file, message.attachments)">
            <span v-if="file.type === 'image' && file.url" class="attachment-preview-frame">
              <img
                :src="file.url"
                :alt="file.name"
                class="attachment-preview-image"
              />
            </span>
            <span v-else :class="attachmentIcon(file)" class="text-sm text-iolite dark:text-iolite-light shrink-0" />
            <span v-if="file.type !== 'image'" class="attachment-meta">
              <span class="attachment-name truncate max-w-[12rem]">{{ file.name }}</span>
              <span v-if="file.size" class="text-warm-400">{{ formatFileSize(file.size) }}</span>
            </span>
          </a>
        </div>
        <div v-if="message.content" class="text-body whitespace-pre-wrap break-words overflow-wrap-anywhere min-w-0 w-full">
          {{ message.content }}
        </div>
      </div>
    </div>
    <!-- Hover actions for user messages -->
    <div v-if="!message.queued && message.conversationIndex != null" class="absolute -bottom-5 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
      <button class="msg-action-btn" title="Copy" aria-label="Copy message" @click="copyMessage">
        <span class="i-carbon-copy text-xs" />
      </button>
      <button class="msg-action-btn" title="Edit in composer" aria-label="Edit message in composer" @click="$emit('request-edit', message)">
        <span class="i-carbon-edit text-xs" />
      </button>
    </div>
  </div>

  <!-- Assistant message (parts-based: ordered text + tools) -->
  <div v-else-if="message.role === 'assistant' && message.parts" class="max-w-[90%] group relative">
    <template v-for="(part, pi) in message.parts" :key="pi">
      <!-- Text part -->
      <div v-if="part.type === 'text' && part.content" class="text-body mb-1">
        <MarkdownRenderer :content="part.content" />
      </div>
      <!-- Tool/subagent part -->
      <div v-else-if="part.type === 'tool'" class="mb-1.5">
        <ToolCallBlock :tc="part" :expanded="expandedTools[part.id]" @toggle="toggleTool(part.id)" />
      </div>
    </template>
    <div
      v-if="assistantRecovering"
      class="inline-flex items-center gap-2 rounded-md border border-iolite/15 dark:border-iolite/20 bg-iolite/6 dark:bg-iolite/8 px-3 py-2 text-xs text-warm-500 dark:text-warm-400"
    >
      <span class="w-1.5 h-1.5 rounded-full bg-iolite kohaku-pulse shrink-0" />
      <span>{{ t("chat.recoveringReply") }}</span>
      <span v-if="message.recoveryAttempt > 0" class="text-[10px] text-warm-400">{{ t("chat.recoveryRetry", { count: message.recoveryAttempt }) }}</span>
    </div>
    <div
      v-else-if="assistantRecoveryFailed"
      class="inline-flex items-center gap-2 rounded-md border border-amber/15 dark:border-amber/20 bg-amber/6 dark:bg-amber/8 px-3 py-2 text-xs text-warm-500 dark:text-warm-400"
    >
      <span class="w-1.5 h-1.5 rounded-full bg-amber shrink-0" />
      <span>{{ t("chat.recoveryFailed") }}</span>
    </div>
    <!-- Hover actions -->
    <div v-if="isLastAssistant" class="absolute -bottom-5 left-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
      <button class="msg-action-btn" title="Copy" aria-label="Copy response" @click="copyAssistantText">
        <span class="i-carbon-copy text-xs" />
      </button>
      <button class="msg-action-btn" title="Regenerate" aria-label="Regenerate response" @click="regenerate">
        <span class="i-carbon-renew text-xs" />
      </button>
    </div>
  </div>

  <!-- Assistant message (legacy: content + tool_calls) -->
  <div v-else-if="message.role === 'assistant'" class="max-w-[90%]">
    <div v-if="message.tool_calls?.length" class="mb-2 flex flex-col gap-1.5">
      <ToolCallBlock v-for="tc in message.tool_calls" :key="tc.id" :tc="tc" :expanded="expandedTools[tc.id]" @toggle="toggleTool(tc.id)" />
    </div>
    <div v-if="message.content" class="text-body">
      <MarkdownRenderer :content="message.content" />
    </div>
  </div>

  <!-- Channel message (group chat style) -->
  <div v-else-if="message.role === 'channel'" class="max-w-[90%]">
    <div v-if="showSenderHeader" class="flex items-center gap-2 mb-1" :class="{ 'mt-2': !isFirst }">
      <span class="w-5 h-5 rounded-md flex items-center justify-center text-[10px] font-bold text-white" :style="{ background: senderGemColor }">
        {{ message.sender.charAt(0).toUpperCase() }}
      </span>
      <span class="text-xs font-semibold" :style="{ color: senderGemColor }">{{ message.sender }}</span>
      <span class="text-[10px] text-warm-400">{{ message.timestamp }}</span>
    </div>
    <div class="pl-7 flex flex-col gap-2">
      <div v-if="message.attachments?.length" class="flex flex-wrap gap-2">
        <a v-for="file in message.attachments" :key="file.id || file.url || file.name" :href="file.url" target="_blank" rel="noreferrer" class="attachment-chip" :class="{ 'attachment-chip-image': file.type === 'image' && file.url }" @click="onAttachmentClick($event, file, message.attachments)">
          <img
            v-if="file.type === 'image' && file.url"
            :src="file.url"
            :alt="file.name"
            class="attachment-preview-image"
          />
          <span v-else :class="attachmentIcon(file)" class="text-sm text-iolite dark:text-iolite-light shrink-0" />
          <span class="attachment-meta">
            <span class="attachment-name truncate max-w-[16rem]">{{ file.name }}</span>
            <span v-if="file.size" class="text-warm-400">{{ formatFileSize(file.size) }}</span>
          </span>
        </a>
      </div>
      <div v-if="message.content" class="text-body">
        <MarkdownRenderer :content="message.content" />
      </div>
    </div>
  </div>

  <el-image-viewer
    v-if="imagePreviewVisible && imagePreviewList.length"
    :url-list="imagePreviewList"
    :initial-index="imagePreviewIndex"
    @close="imagePreviewVisible = false"
  />
</template>

<script setup>
import MarkdownRenderer from "@/components/common/MarkdownRenderer.vue"
import ToolCallBlock from "@/components/chat/ToolCallBlock.vue"
import { GEM } from "@/utils/colors"
import { useChatStore } from "@/stores/chat"
import { useI18n } from "@/utils/i18n"

const props = defineProps({
  message: { type: Object, required: true },
  prevMessage: { type: Object, default: null },
  isFirst: { type: Boolean, default: false },
  messageIdx: { type: Number, default: null },
  isLastAssistant: { type: Boolean, default: false },
})

defineEmits(["request-edit"])

const { t } = useI18n()

const expandedTools = reactive({})
const errorExpanded = ref(false)
const imagePreviewVisible = ref(false)
const imagePreviewIndex = ref(0)
const imagePreviewList = ref([])

const errorFirstLine = computed(() => {
  if (props.message.role !== "error") return ""
  const content = props.message.content || ""
  const firstLine = content.split("\n")[0] || ""
  return firstLine.length > 80 ? firstLine.slice(0, 80) + "…" : firstLine
})

const assistantRecovering = computed(() => {
  if (props.message.role !== "assistant") return false
  if (!props.message.recovering) return false
  const hasText = Array.isArray(props.message.parts)
    ? props.message.parts.some((part) => part.type === "text" && part.content)
    : !!props.message.content
  return !hasText
})

const assistantRecoveryFailed = computed(() => {
  if (props.message.role !== "assistant") return false
  if (!props.message.recoveryFailed) return false
  const hasText = Array.isArray(props.message.parts)
    ? props.message.parts.some((part) => part.type === "text" && part.content)
    : !!props.message.content
  return !hasText
})

function toggleTool(id) {
  expandedTools[id] = !expandedTools[id]
}

const showSenderHeader = computed(() => {
  if (props.message.role !== "channel") return false
  if (!props.prevMessage || props.prevMessage.role !== "channel") return true
  return props.prevMessage.sender !== props.message.sender
})

const SENDER_GEMS = [GEM.iolite.main, GEM.aquamarine.main, GEM.taaffeite.main, GEM.amber.main, GEM.sapphire.main]
const senderColorCache = {}
let nextColorIdx = 0

const senderGemColor = computed(() => {
  const name = props.message.sender
  if (!name) return GEM.iolite.main
  if (!senderColorCache[name]) {
    senderColorCache[name] = SENDER_GEMS[nextColorIdx % SENDER_GEMS.length]
    nextColorIdx++
  }
  return senderColorCache[name]
})

function formatFileSize(size) {
  if (!size) return ""
  if (size >= 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`
  if (size >= 1024) return `${Math.round(size / 1024)} KB`
  return `${size} B`
}

function attachmentIcon(file) {
  if (file.type === "image") return "i-carbon-image"
  if (file.type === "video") return "i-carbon-video"
  if (file.type === "pdf") return "i-carbon-document-pdf"
  return "i-carbon-document"
}

function onAttachmentClick(event, file, attachments = []) {
  if (file.type !== "image" || !file.url) return
  event.preventDefault()
  const images = attachments.filter((item) => item.type === "image" && item.url)
  imagePreviewList.value = images.map((item) => item.url)
  imagePreviewIndex.value = Math.max(
    0,
    images.findIndex((item) => item.url === file.url),
  )
  imagePreviewVisible.value = true
}

const chat = useChatStore()

function copyMessage() {
  const text = props.message.content || ""
  navigator.clipboard.writeText(text)
}

function copyAssistantText() {
  let text = ""
  if (props.message.parts) {
    for (const part of props.message.parts) {
      if (part.type === "text" && part.content) {
        text += part.content
      }
    }
  } else if (props.message.content) {
    text = props.message.content
  }
  navigator.clipboard.writeText(text)
}

function regenerate() {
  chat.regenerateLastResponse()
}
</script>

<style scoped>
.attachment-chip {
  display: inline-flex;
  flex-direction: row;
  align-items: center;
  gap: 0.5rem;
  max-width: 100%;
  padding: 0.5rem 0.625rem;
  border-radius: 0.75rem;
  border: 1px solid rgba(120, 109, 98, 0.22);
  background: rgba(255, 255, 255, 0.03);
  color: inherit;
  text-decoration: none;
  transition:
    border-color 0.15s,
    background 0.15s,
    transform 0.15s;
}

.attachment-chip:hover {
  border-color: rgba(125, 108, 255, 0.35);
  background: rgba(125, 108, 255, 0.06);
}

.attachment-chip-image {
  cursor: zoom-in;
  flex-direction: column;
  align-items: stretch;
  gap: 0.25rem;
  width: auto;
  max-width: 10rem;
  padding: 0.375rem;
}

.attachment-chip-image:hover {
  transform: translateY(-1px);
}

.attachment-preview-frame {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 6rem;
  height: 6rem;
  border-radius: 0.5rem;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.04);
}

.attachment-preview-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  background: rgba(255, 255, 255, 0.04);
}

.attachment-meta {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}

.attachment-chip-image .attachment-meta {
  display: flex;
  justify-content: space-between;
}

.attachment-name {
  color: inherit;
}

.msg-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 4px;
  background: var(--color-card);
  border: 1px solid var(--color-border);
  color: var(--color-text-muted);
  cursor: pointer;
  transition:
    background 0.15s,
    color 0.15s,
    border-color 0.15s;
}
.msg-action-btn:hover {
  background: var(--color-card-hover);
  color: var(--color-text);
  border-color: var(--color-border-hover);
}
</style>
