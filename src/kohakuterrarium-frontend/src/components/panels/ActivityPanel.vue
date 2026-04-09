<template>
  <div class="h-full flex flex-col bg-warm-50 dark:bg-warm-900 overflow-hidden">
    <!-- Panel header -->
    <div
      class="flex items-center gap-2 px-3 py-2 border-b border-warm-200 dark:border-warm-700 shrink-0"
    >
      <div class="i-carbon-pulse text-sm text-warm-500" />
      <span class="text-xs font-medium text-warm-500 dark:text-warm-400 flex-1">Activity</span>
      <span
        v-if="jobCount > 0"
        class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber/15 text-amber"
      >{{ jobCount }}</span>
    </div>

    <!-- Body: running jobs list, read straight from chat store. -->
    <div class="flex-1 overflow-y-auto px-3 py-2 text-xs">
      <div
        v-if="jobCount === 0"
        class="text-warm-400 py-6 text-center"
      >
        No running jobs
      </div>
      <div v-else class="flex flex-col gap-1.5">
        <div
          v-for="(job, jobId) in chat.runningJobs"
          :key="jobId"
          class="flex items-center gap-2 px-2 py-1.5 rounded-md bg-amber/10 group"
        >
          <span class="w-1.5 h-1.5 rounded-full bg-amber kohaku-pulse shrink-0" />
          <span
            class="font-mono text-[11px] text-amber-shadow dark:text-amber-light truncate"
          >{{ job.name }}</span>
          <span class="flex-1" />
          <span class="text-warm-400 font-mono text-[10px]">
            {{ chat.getJobElapsed(job) }}
          </span>
          <button
            class="text-warm-400 hover:text-coral transition-colors opacity-0 group-hover:opacity-100"
            title="Stop task"
            @click="stopJob(jobId, job.name)"
          >
            <span class="i-carbon-close text-[10px]" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";

import { useChatStore } from "@/stores/chat";
import { agentAPI } from "@/utils/api";

const props = defineProps({
  instance: { type: Object, default: null },
});

const chat = useChatStore();

const jobCount = computed(() => Object.keys(chat.runningJobs || {}).length);

async function stopJob(jobId, name) {
  const agentId = props.instance?.id;
  if (!agentId) return;
  try {
    await agentAPI.stopTask(agentId, jobId);
  } catch (err) {
    console.error("Failed to stop job", name, err);
  }
}
</script>
