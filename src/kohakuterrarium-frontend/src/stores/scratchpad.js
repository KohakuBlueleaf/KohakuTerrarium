/**
 * Scratchpad store — talks to the Phase 1 read-only API to fetch and
 * patch an agent's scratchpad. Polls on a short interval while the
 * panel is mounted so values stay in sync.
 */

import { defineStore } from "pinia";
import { ref } from "vue";

import { agentAPI } from "@/utils/api";

export const useScratchpadStore = defineStore("scratchpad", () => {
  const byAgent = ref(/** @type {Record<string, Record<string, string>>} */ ({}));
  const loading = ref(/** @type {Record<string, boolean>} */ ({}));
  const error = ref(/** @type {Record<string, string>} */ ({}));
  const pollTimers = ref(/** @type {Record<string, any>} */ ({}));

  async function fetch(agentId) {
    if (!agentId) return;
    loading.value = { ...loading.value, [agentId]: true };
    try {
      const data = await agentAPI.getScratchpad(agentId);
      byAgent.value = { ...byAgent.value, [agentId]: data };
      const next = { ...error.value };
      delete next[agentId];
      error.value = next;
    } catch (err) {
      error.value = { ...error.value, [agentId]: String(err?.message || err) };
    } finally {
      loading.value = { ...loading.value, [agentId]: false };
    }
  }

  async function patch(agentId, updates) {
    if (!agentId) return;
    const data = await agentAPI.patchScratchpad(agentId, updates);
    byAgent.value = { ...byAgent.value, [agentId]: data };
    return data;
  }

  function startPolling(agentId, intervalMs = 4000) {
    stopPolling(agentId);
    fetch(agentId);
    pollTimers.value[agentId] = setInterval(() => fetch(agentId), intervalMs);
  }

  function stopPolling(agentId) {
    const t = pollTimers.value[agentId];
    if (t) {
      clearInterval(t);
      const next = { ...pollTimers.value };
      delete next[agentId];
      pollTimers.value = next;
    }
  }

  function getFor(agentId) {
    return byAgent.value[agentId] || {};
  }

  return {
    byAgent,
    loading,
    error,
    fetch,
    patch,
    startPolling,
    stopPolling,
    getFor,
  };
});
