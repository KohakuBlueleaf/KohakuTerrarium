<template>
  <!--
    Panel bg = recessed surface (warm-100 / warm-900)
    Bubble bg = header-level surface (white / warm-800)
    Tab bar sits on panel bg, active tab = bubble bg
    Bubble has equal margin left/right/bottom
  -->
  <div class="h-full flex flex-col bg-warm-100 dark:bg-[#211F1D]">
    <!-- Tab bar on panel bg -->
    <div class="flex items-end gap-0 px-4 pt-2 shrink-0">
      <div
        v-for="tab in chat.tabs"
        :key="tab"
        class="relative flex items-center gap-1.5 px-3.5 py-2 text-xs font-medium cursor-pointer select-none rounded-t-lg -mb-px transition-colors"
        :class="
          chat.activeTab === tab
            ? 'bg-white dark:bg-warm-900 text-warm-800 dark:text-warm-200 border border-warm-200 dark:border-warm-700 border-b-white dark:border-b-warm-900 z-10'
            : 'text-warm-400 dark:text-warm-500 hover:text-warm-600 dark:hover:text-warm-400 border border-transparent'
        "
        @click="chat.setActiveTab(tab)"
      >
        <template v-if="tab === 'root'">
          <span class="w-2 h-2 rounded-full bg-amber shrink-0" />
          <span>Root Agent</span>
        </template>
        <template v-else-if="tab.startsWith('ch:')">
          <span class="text-aquamarine font-bold shrink-0">&rarr;</span>
          <span>{{ tab.slice(3) }}</span>
          <span
            v-if="chat.unreadCounts[tab]"
            class="ml-1 px-1.5 py-0.5 rounded-full bg-amber text-white text-[9px] font-bold leading-none"
            >{{ chat.unreadCounts[tab] }}</span
          >
        </template>
        <template v-else>
          <StatusDot :status="getCreatureStatus(tab)" />
          <span>{{ tab }}</span>
        </template>

        <button
          v-if="tab !== 'root' && chat.tabs.length > 1"
          class="ml-1 w-4 h-4 flex items-center justify-center rounded-sm text-warm-400 hover:text-warm-600 dark:hover:text-warm-300 transition-colors"
          @click.stop="closeTab(tab)"
        >
          <div class="i-carbon-close text-[10px]" />
        </button>
      </div>

      <!-- Token usage + session info for active tab -->
      <div
        v-if="activeTokens > 0 || chat.sessionInfo.model"
        class="flex items-center gap-2 px-2 py-2 -mb-px text-[10px] text-warm-400 font-mono"
      >
        <template v-if="chat.sessionInfo.model">
          <span class="text-warm-500 dark:text-warm-400">{{ chat.sessionInfo.model }}</span>
          <span class="text-warm-300 dark:text-warm-600">|</span>
        </template>
        <template v-if="activeTokens > 0">
          <span class="i-carbon-meter text-amber" />
          <span title="Cumulative input tokens">In: {{ formatTokens(activeUsage.prompt) }}</span>
          <span v-if="activeUsage.cached > 0" class="text-aquamarine" title="Cached input tokens">(cache {{ formatTokens(activeUsage.cached) }})</span>
          <span title="Cumulative output tokens">Out: {{ formatTokens(activeUsage.completion) }}</span>
        </template>
        <template v-if="chat.sessionInfo.compactThreshold > 0 && activeUsage.prompt > 0">
          <span class="text-warm-300 dark:text-warm-600">|</span>
          <span
            :class="contextPct >= 80 ? 'text-coral' : contextPct >= 60 ? 'text-amber' : ''"
            :title="`Context: ${formatTokens(activeUsage.prompt)} / ${formatTokens(chat.sessionInfo.compactThreshold)}`"
          >Ctx: {{ contextPct }}%</span>
        </template>
      </div>

      <!-- Tab bar bottom border (bubble top border) -->
      <div class="flex-1 border-b border-b-warm-200 dark:border-b-warm-700" />
    </div>

    <!-- Chat bubble: surface-level bg, equal margin left/right/bottom -->
    <div
      class="flex-1 mx-4 mb-4 bg-white dark:bg-warm-900 rounded-b-xl rounded-tr-xl border border-warm-200 dark:border-warm-700 border-t-0 overflow-hidden flex flex-col shadow-sm"
    >
      <!-- Decorative top accent: subtle gem gradient -->
      <div
        class="h-0.5 w-full bg-gradient-to-r from-iolite/30 via-taaffeite/20 to-aquamarine/30"
      />

      <!-- Messages -->
      <div ref="messagesEl" class="flex-1 overflow-y-auto px-5 py-4">
        <div class="flex flex-col gap-3">
          <template v-if="chat.currentMessages.length === 0">
            <div class="text-center py-16">
              <div
                class="w-12 h-12 rounded-2xl bg-gradient-to-br from-iolite/10 to-amber/10 dark:from-iolite/5 dark:to-amber/5 flex items-center justify-center mx-auto mb-3"
              >
                <div
                  class="i-carbon-chat text-xl text-iolite/40 dark:text-iolite-light/30"
                />
              </div>
              <p class="text-warm-400 dark:text-warm-500 text-sm">
                No messages yet
              </p>
              <p class="text-warm-300 dark:text-warm-600 text-xs mt-1">
                Send a message to get started
              </p>
            </div>
          </template>
          <ChatMessage
            v-for="(msg, idx) in chat.currentMessages"
            :key="msg.id"
            :message="msg"
            :prev-message="idx > 0 ? chat.currentMessages[idx - 1] : null"
            :is-first="idx === 0"
          />
          <div
            v-if="chat.processing"
            class="flex items-center gap-2.5 py-2 pl-1"
          >
            <span class="w-2 h-2 rounded-full bg-amber kohaku-glow" />
            <span class="text-sm text-amber/80 kohaku-pulse"
              >KohakUwUing...</span
            >
          </div>
        </div>
      </div>

      <!-- Running tasks -->
      <div
        v-if="chat.hasRunningJobs"
        class="px-4 py-1.5 border-t border-t-warm-100 dark:border-t-warm-800 bg-warm-50/50 dark:bg-warm-800/30"
      >
        <div class="flex items-center gap-1.5 text-[10px] text-warm-400 mb-1">
          <span class="i-carbon-in-progress text-amber" />
          <span>Running tasks</span>
        </div>
        <div class="flex flex-wrap gap-1.5">
          <div
            v-for="(job, jobId) in chat.runningJobs"
            :key="jobId"
            class="flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber/10 text-[11px] font-mono"
          >
            <span class="w-1.5 h-1.5 rounded-full bg-amber kohaku-pulse" />
            <span class="text-amber-shadow dark:text-amber-light">{{
              job.name
            }}</span>
            <span class="text-warm-400">{{
              Math.floor((Date.now() - job.startedAt) / 1000)
            }}s</span>
            <button
              class="ml-0.5 text-warm-400 hover:text-coral transition-colors"
              title="Stop task"
              @click="stopTask(jobId, job.name)"
            >
              <span class="i-carbon-close text-[9px]" />
            </button>
          </div>
        </div>
      </div>

      <!-- Input: sits inside bubble, with subtle top border -->
      <div
        class="px-4 pb-4 pt-2 border-t border-t-warm-100 dark:border-t-warm-800"
      >
        <div
          class="flex gap-2 px-3 py-1.5 rounded-xl bg-warm-50 dark:bg-warm-800 border border-warm-200 dark:border-warm-700 focus-within:border-iolite/40 dark:focus-within:border-iolite-light/30 transition-colors"
          :class="inputText.includes('\n') ? 'items-end' : 'items-center'"
        >
          <textarea
            ref="inputEl"
            v-model="inputText"
            rows="1"
            class="flex-1 bg-transparent border-none outline-none text-sm text-warm-800 dark:text-warm-200 placeholder-warm-400 dark:placeholder-warm-500 resize-none max-h-32 leading-relaxed py-1"
            style="min-height: 2em"
            :placeholder="inputPlaceholder"
            @keydown="onInputKeydown"
            @input="autoResize"
          />
          <button
            v-if="chat.processing || chat.hasRunningJobs"
            class="w-8 h-8 flex items-center justify-center rounded-lg transition-all shrink-0 mb-0.5 bg-coral/90 text-white hover:bg-coral shadow-sm shadow-coral/20"
            title="Stop generation (Esc)"
            @click="chat.interrupt()"
          >
            <span class="i-carbon-stop-filled text-sm" />
          </button>
          <button
            v-else
            class="w-8 h-8 flex items-center justify-center rounded-lg transition-all shrink-0 mb-0.5"
            :class="
              inputText.trim()
                ? 'bg-iolite text-white hover:bg-iolite-shadow shadow-sm shadow-iolite/20'
                : 'text-warm-300 dark:text-warm-600 cursor-not-allowed'
            "
            :disabled="!inputText.trim()"
            @click="send"
          >
            <span class="i-carbon-send text-sm" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import StatusDot from "@/components/common/StatusDot.vue";
import ChatMessage from "@/components/chat/ChatMessage.vue";
import { useChatStore } from "@/stores/chat";
import { terrariumAPI, agentAPI } from "@/utils/api";

const props = defineProps({
  instance: { type: Object, required: true },
});

const chat = useChatStore();
const inputText = ref("");
const messagesEl = ref(null);
const inputEl = ref(null);

const activeUsage = computed(() => {
  const tab = chat.activeTab;
  if (!tab) return { prompt: 0, completion: 0, total: 0 };
  return chat.tokenUsage[tab] || { prompt: 0, completion: 0, total: 0 };
});

const activeTokens = computed(() => activeUsage.value.total);

const contextPct = computed(() => {
  const threshold = chat.sessionInfo.compactThreshold;
  if (!threshold || !activeUsage.value.prompt) return 0;
  return Math.min(100, Math.round((activeUsage.value.prompt / threshold) * 100));
});

function formatTokens(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
  if (n >= 1000) return (n / 1000).toFixed(1) + "K";
  return String(n);
}

const inputPlaceholder = computed(() => {
  if (!chat.activeTab) return "Select a tab...";
  if (chat.activeTab === "root") return "Message the root agent...";
  if (chat.activeTab.startsWith("ch:"))
    return `Send to ${chat.activeTab.slice(3)} channel...`;
  return `Message ${chat.activeTab}...`;
});

function getCreatureStatus(name) {
  const creature = props.instance.creatures.find((c) => c.name === name);
  return creature?.status || "idle";
}

function closeTab(tab) {
  const idx = chat.tabs.indexOf(tab);
  if (idx === -1) return;
  chat.tabs.splice(idx, 1);
  if (chat.activeTab === tab) {
    chat.setActiveTab(chat.tabs[Math.min(idx, chat.tabs.length - 1)] || null);
  }
}

function onInputKeydown(e) {
  if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey) {
    e.preventDefault();
    send();
  }
  // Shift+Enter and Ctrl+Enter insert newline (default textarea behavior)
}

function autoResize() {
  const el = inputEl.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 128) + "px";
}

function send() {
  if (!inputText.value.trim()) return;
  chat.send(inputText.value);
  inputText.value = "";
  nextTick(() => {
    if (inputEl.value) inputEl.value.style.height = "auto";
    if (messagesEl.value)
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight;
  });
}

async function stopTask(jobId, jobName) {
  try {
    const tab = chat.activeTab;
    if (chat._instanceType === "terrarium") {
      await terrariumAPI.stopCreatureTask(chat._instanceId, tab || "root", jobId);
    } else {
      await agentAPI.stopTask(chat._instanceId, jobId);
    }
    delete chat.runningJobs[jobId];
  } catch (err) {
    console.error("Failed to stop task:", err);
  }
}

// Escape key interrupt
function onGlobalKeydown(e) {
  if (e.key === "Escape" && (chat.processing || chat.hasRunningJobs)) {
    chat.interrupt();
  }
}
onMounted(() => window.addEventListener("keydown", onGlobalKeydown));
onUnmounted(() => window.removeEventListener("keydown", onGlobalKeydown));
</script>
