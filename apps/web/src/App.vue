<template>
  <div class="h-screen flex overflow-hidden bg-warm-50 dark:bg-warm-950">
    <NavRail />
    <main class="flex-1 overflow-hidden">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup>
import NavRail from "@/components/layout/NavRail.vue";
import { useThemeStore } from "@/stores/theme";

const theme = useThemeStore();
theme.init();
</script>
