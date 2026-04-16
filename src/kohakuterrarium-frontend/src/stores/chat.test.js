import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it } from "vitest"

import { agentAPI } from "@/utils/api"
import { _replayEvents, useChatStore } from "./chat.js"

beforeEach(() => {
  setActivePinia(createPinia())
})

describe("chat store — interrupted task handling", () => {
  it("replays interrupted tool_result as interrupted instead of running", () => {
    const chat = useChatStore()
    chat.messagesByTab = { main: [] }

    const messages = []
    const events = [
      { type: "processing_start" },
      { type: "tool_call", name: "bash", call_id: "job_1", args: { command: "sleep 10" } },
      {
        type: "tool_result",
        name: "bash",
        call_id: "job_1",
        output: "User manually interrupted this job.",
        error: "User manually interrupted this job.",
        interrupted: true,
        final_state: "interrupted",
      },
      { type: "processing_end" },
    ]

    const { messages: replayed, pendingJobs } = _replayEvents(messages, events)

    const tool = replayed[0].parts[0]
    expect(tool.status).toBe("interrupted")
    expect(tool.result).toBe("User manually interrupted this job.")
    expect(pendingJobs).toEqual({})
  })

  it("replays interrupted subagent_result as interrupted instead of running", () => {
    const chat = useChatStore()
    chat.messagesByTab = { main: [] }

    const messages = []
    const events = [
      { type: "processing_start" },
      { type: "subagent_call", name: "explore", job_id: "agent_explore_1", task: "find auth" },
      {
        type: "subagent_result",
        name: "explore",
        job_id: "agent_explore_1",
        output: "User manually interrupted this job.",
        error: "User manually interrupted this job.",
        interrupted: true,
        final_state: "interrupted",
      },
      { type: "processing_end" },
    ]

    const { messages: replayed, pendingJobs } = _replayEvents(messages, events)

    const tool = replayed[0].parts[0]
    expect(tool.status).toBe("interrupted")
    expect(pendingJobs).toEqual({})
  })

  it("live tool_error with interrupted metadata clears running job as interrupted", () => {
    const chat = useChatStore()
    chat.messagesByTab = { main: [{ id: "m1", role: "assistant", parts: [] }] }
    chat.activeTab = "main"

    chat._handleActivity("main", {
      activity_type: "tool_start",
      name: "bash",
      job_id: "job_1",
      args: { command: "sleep 10" },
      background: false,
      id: "tc_1",
    })

    chat._handleActivity("main", {
      activity_type: "tool_error",
      name: "bash",
      job_id: "job_1",
      interrupted: true,
      final_state: "interrupted",
      error: "User manually interrupted this job.",
      result: "User manually interrupted this job.",
    })

    const tool = chat._findToolPart(chat.messagesByTab.main, "bash", "job_1")
    expect(tool.status).toBe("interrupted")
    expect(tool.result).toBe("User manually interrupted this job.")
    expect(chat.runningJobs.job_1).toBeUndefined()
  })

  it("does not infer interrupted for subagents without explicit interruption metadata", () => {
    const { messages: replayed, pendingJobs } = _replayEvents([], [
      { type: "processing_start" },
      { type: "subagent_call", name: "explore", task: "find auth" },
      { type: "processing_end" },
    ])

    const tool = replayed[0].parts[0]
    expect(tool).toMatchObject({
      type: "tool",
      kind: "subagent",
      name: "explore",
      status: "done",
      result: "",
      jobId: "",
    })
    expect(pendingJobs).toEqual({})
  })
})

describe("chat store — standalone agent history loading", () => {
  it("rebuilds messages from event-only agent history responses", async () => {
    const chat = useChatStore()
    chat._instanceGeneration = 1
    chat.messagesByTab = { main: [] }

    const originalGetHistory = agentAPI.getHistory
    agentAPI.getHistory = async () => ({
      agent_id: "agent_1",
      events: [
        { type: "user_input", content: "hello" },
        { type: "processing_start" },
        { type: "text", content: "world" },
        { type: "processing_end" },
      ],
    })

    try {
      await chat._loadAgentHistory("agent_1", "main", 1)
    } finally {
      agentAPI.getHistory = originalGetHistory
    }

    expect(chat.messagesByTab.main).toHaveLength(2)
    expect(chat.messagesByTab.main[0]).toMatchObject({ role: "user", content: "hello" })
    expect(chat.messagesByTab.main[1].role).toBe("assistant")
    expect(chat.messagesByTab.main[1].parts).toEqual([{ type: "text", content: "world", _streaming: false }])
  })
})

describe("chat store — standalone agent empty completion recovery", () => {
  it("resyncs history when a standalone agent finishes with an empty assistant message", async () => {
    const chat = useChatStore()
    chat._instanceId = "agent_1"
    chat._instanceType = "agent"
    chat.activeTab = "main"
    chat.messagesByTab = {
      main: [
        {
          id: "m1",
          role: "assistant",
          parts: [],
          _streaming: true,
        },
      ],
    }

    const calls = []
    const originalStartRecoveryPolling = chat._startRecoveryPolling
    chat._startRecoveryPolling = function () {
      calls.push(chat._instanceId)
      chat.messagesByTab.main = [
        { id: "u1", role: "user", content: "这是啥？" },
        {
          id: "a1",
          role: "assistant",
          parts: [{ type: "text", content: "这是 Chrome 新标签页。", _streaming: false }],
        },
      ]
    }

    try {
      chat._finishStream("main")
      await Promise.resolve()
      await Promise.resolve()
    } finally {
      chat._startRecoveryPolling = originalStartRecoveryPolling
    }

    expect(calls).toEqual(["agent_1"])
    expect(chat.messagesByTab.main).toHaveLength(2)
    expect(chat.messagesByTab.main[1]).toMatchObject({
      role: "assistant",
      parts: [{ type: "text", content: "这是 Chrome 新标签页。", _streaming: false }],
    })
  })

  it("does not resync history when the standalone agent already streamed visible text", async () => {
    const chat = useChatStore()
    chat._instanceId = "agent_1"
    chat._instanceType = "agent"
    chat.activeTab = "main"
    chat.messagesByTab = {
      main: [
        {
          id: "m1",
          role: "assistant",
          parts: [{ type: "text", content: "partial", _streaming: true }],
          _streaming: true,
        },
      ],
    }

    const calls = []
    const originalGetHistory = agentAPI.getHistory
    agentAPI.getHistory = async (id) => {
      calls.push(id)
      return { agent_id: id, events: [] }
    }

    try {
      chat._finishStream("main")
      await Promise.resolve()
    } finally {
      agentAPI.getHistory = originalGetHistory
    }

    expect(calls).toEqual([])
    expect(chat.messagesByTab.main[0]).toMatchObject({
      role: "assistant",
      parts: [{ type: "text", content: "partial", _streaming: false }],
      _streaming: false,
    })
  })
})

describe("chat store — compact round handling", () => {
  it("replays compact start/complete as a single merged compact message", () => {
    const { messages: replayed } = _replayEvents(
      [],
      [
        { type: "compact_start", round: 9 },
        {
          type: "compact_complete",
          round: 9,
          summary: "summary text",
          messages_compacted: 7,
        },
      ],
    )

    expect(replayed).toHaveLength(1)
    expect(replayed[0]).toMatchObject({
      role: "compact",
      round: 9,
      summary: "summary text",
      status: "done",
      messagesCompacted: 7,
    })
  })

  it("merges live compact start/complete for the same round", () => {
    const chat = useChatStore()
    chat.messagesByTab = { main: [] }
    chat.activeTab = "main"

    chat._handleActivity("main", {
      activity_type: "compact_start",
      round: 2,
    })
    chat._handleActivity("main", {
      activity_type: "compact_complete",
      round: 2,
      summary: "merged summary",
      messages_compacted: 12,
    })

    expect(chat.messagesByTab.main).toHaveLength(1)
    expect(chat.messagesByTab.main[0]).toMatchObject({
      role: "compact",
      round: 2,
      summary: "merged summary",
      status: "done",
      messagesCompacted: 12,
    })
  })
})
