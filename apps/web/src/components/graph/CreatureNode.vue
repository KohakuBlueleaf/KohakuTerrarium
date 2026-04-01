<template>
  <div class="creature-node">
    <Handle
      id="left"
      type="target"
      :position="Position.Left"
      class="creature-handle"
      :style="handleStyle"
    />
    <Handle
      id="right"
      type="source"
      :position="Position.Right"
      class="creature-handle"
      :style="handleStyle"
    />
    <Handle
      id="top"
      type="source"
      :position="Position.Top"
      class="creature-handle creature-handle--group"
      :style="groupHandleStyle"
    />
    <Handle
      id="bottom"
      type="target"
      :position="Position.Bottom"
      class="creature-handle creature-handle--group"
      :style="groupHandleStyle"
    />

    <div class="creature-body" :style="bodyStyle">
      <span class="creature-dot" :style="{ backgroundColor: dotColor }" />
      <span class="creature-name" :style="{ color: nameColor }">{{
        data.name
      }}</span>
    </div>
  </div>
</template>

<script setup>
import { Handle, Position } from "@vue-flow/core";
import { statusColor } from "@/utils/colors";
import { useThemeStore } from "@/stores/theme";

const props = defineProps({
  data: { type: Object, required: true },
});

const theme = useThemeStore();

const dotColor = computed(() => statusColor(props.data.status).main);

const bodyStyle = computed(() => ({
  background: theme.dark ? "#252230" : "#FAF7F5",
  borderColor: theme.dark ? "#7B6FE0" : "#5A4FCF",
}));

const handleStyle = computed(() => ({
  background: theme.dark ? "#7B6FE0" : "#5A4FCF",
  borderColor: theme.dark ? "#252230" : "#FAF7F5",
}));

const groupHandleStyle = computed(() => ({
  background: theme.dark ? "#C49ECF" : "#A57EAE",
  borderColor: theme.dark ? "#252230" : "#FAF7F5",
}));

const nameColor = computed(() => (theme.dark ? "#E8E0D8" : "#3A3632"));
</script>

<style scoped>
.creature-body {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border: 2px solid;
  border-radius: 12px;
  cursor: pointer;
  transition:
    box-shadow 0.15s ease,
    background 0.2s ease,
    border-color 0.2s ease;
  min-width: 100px;
}
.creature-body:hover {
  box-shadow: 0 0 0 3px rgba(90, 79, 207, 0.15);
}
.creature-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  transition: background-color 0.2s ease;
}
.creature-name {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  transition: color 0.2s ease;
}
.creature-handle {
  width: 7px;
  height: 7px;
  border: 2px solid;
  border-radius: 50%;
  transition:
    background 0.2s ease,
    border-color 0.2s ease;
}
.creature-handle--group {
  width: 6px;
  height: 6px;
}
</style>
