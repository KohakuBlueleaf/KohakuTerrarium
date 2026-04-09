<template>
  <div class="h-full flex flex-col bg-warm-50 dark:bg-warm-900">
    <!-- Panel header -->
    <div
      class="flex items-center gap-2 px-3 py-2 border-b border-warm-200 dark:border-warm-700 shrink-0"
    >
      <div class="i-carbon-folder text-sm text-warm-500" />
      <span class="text-xs font-medium text-warm-500 dark:text-warm-400 truncate flex-1">Files</span>
      <button
        class="w-6 h-6 flex items-center justify-center rounded text-warm-400 hover:text-warm-600 dark:hover:text-warm-300 transition-colors"
        title="Refresh"
        @click="treeRef?.refresh()"
      >
        <div class="i-carbon-renew text-sm" />
      </button>
    </div>

    <!-- Body: existing FileTree, unchanged -->
    <div class="flex-1 min-h-0">
      <FileTree
        ref="treeRef"
        :root="root"
        @select="onSelect"
      />
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";

import FileTree from "@/components/editor/FileTree.vue";

const props = defineProps({
  root: { type: String, required: true },
  onSelect: { type: Function, default: () => {} },
});

const treeRef = ref(null);
</script>
