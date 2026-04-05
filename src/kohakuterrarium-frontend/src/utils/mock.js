/**
 * Mock data for frontend development.
 * Replace with real API calls in Phase 3.
 */

/** @type {import('./api').ConfigItem[]} */
export const MOCK_CREATURE_CONFIGS = [
  {
    name: "general",
    path: "creatures/general",
    description: "General purpose assistant",
  },
  {
    name: "swe",
    path: "creatures/swe",
    description: "Software engineering agent",
  },
  {
    name: "reviewer",
    path: "creatures/reviewer",
    description: "Code review specialist",
  },
  {
    name: "researcher",
    path: "creatures/researcher",
    description: "Research and analysis agent",
  },
  {
    name: "creative",
    path: "creatures/creative",
    description: "Creative writing agent",
  },
  {
    name: "ops",
    path: "creatures/ops",
    description: "Infrastructure and operations agent",
  },
];

/** @type {import('./api').ConfigItem[]} */
export const MOCK_TERRARIUM_CONFIGS = [
  {
    name: "swe_team",
    path: "terrariums/swe_team",
    description: "SWE + Reviewer collaborative team",
  },
];

/** @type {import('./api').InstanceInfo[]} */
export const MOCK_INSTANCES = [
  {
    id: "inst_001",
    type: "terrarium",
    config_name: "swe_team",
    config_path: "terrariums/swe_team",
    pwd: "/home/user/my-project",
    status: "running",
    has_root: true,
    creatures: [
      {
        name: "swe",
        status: "running",
        model: "google/gemini-3-flash-preview",
        listen_channels: ["tasks", "feedback", "team_chat", "swe"],
        send_channels: ["review", "team_chat"],
      },
      {
        name: "reviewer",
        status: "idle",
        model: "google/gemini-3-flash-preview",
        listen_channels: ["review", "team_chat", "reviewer"],
        send_channels: ["feedback", "results", "team_chat"],
      },
    ],
    channels: [
      {
        name: "tasks",
        type: "queue",
        description: "Task assignments",
        message_count: 3,
      },
      {
        name: "review",
        type: "queue",
        description: "Code for review",
        message_count: 1,
      },
      {
        name: "feedback",
        type: "queue",
        description: "Review feedback",
        message_count: 0,
      },
      {
        name: "results",
        type: "queue",
        description: "Approved results",
        message_count: 2,
      },
      {
        name: "team_chat",
        type: "broadcast",
        description: "Team-wide discussion",
        message_count: 5,
      },
      {
        name: "swe",
        type: "queue",
        description: "Direct channel for swe",
        message_count: 0,
      },
      {
        name: "reviewer",
        type: "queue",
        description: "Direct channel for reviewer",
        message_count: 0,
      },
    ],
    created_at: "2026-04-01T10:30:00Z",
  },
  {
    id: "inst_002",
    type: "creature",
    config_name: "swe",
    config_path: "creatures/swe",
    pwd: "/home/user/another-project",
    status: "running",
    has_root: false,
    creatures: [
      {
        name: "swe_agent",
        status: "running",
        model: "google/gemini-3-flash-preview",
        listen_channels: [],
        send_channels: [],
      },
    ],
    channels: [],
    created_at: "2026-04-01T11:15:00Z",
  },
];

/** @returns {import('./api').ChatMessage[]} */
export function getMockChatMessages() {
  return [
    {
      id: "msg_001",
      role: "system",
      content: "Connected to Root Agent (swe_team)",
      timestamp: "2026-04-01T10:30:05Z",
    },
    {
      id: "msg_002",
      role: "user",
      content:
        "Fix the authentication bug in src/auth/middleware.py - the session token validation is missing the expiry check.",
      timestamp: "2026-04-01T10:31:00Z",
    },
    {
      id: "msg_003",
      role: "assistant",
      content:
        "I'll dispatch this task to the SWE creature to investigate and fix the authentication issue.",
      timestamp: "2026-04-01T10:31:02Z",
      tool_calls: [
        {
          id: "tc_001",
          name: "terrarium_send",
          args: {
            channel: "tasks",
            content:
              "Fix the authentication bug in src/auth/middleware.py - session token validation missing expiry check.",
          },
          status: "done",
          result: "Message sent to channel 'tasks' (msg_id: ch_msg_001)",
        },
      ],
    },
    {
      id: "msg_004",
      role: "assistant",
      content:
        "Task dispatched to the SWE creature via the tasks channel. I'll set up observation on the results channel to monitor progress.",
      timestamp: "2026-04-01T10:31:05Z",
      tool_calls: [
        {
          id: "tc_002",
          name: "terrarium_observe",
          args: { channels: ["results", "feedback"] },
          status: "done",
          result: "Now observing channels: results, feedback",
        },
      ],
    },
    {
      id: "msg_005",
      role: "assistant",
      content:
        "The SWE creature is now working on the task. I'll notify you when results come through the feedback or results channels.",
      timestamp: "2026-04-01T10:31:08Z",
    },
  ];
}

/** @returns {{ creature: string, output: string, timestamp: string }[]} */
export function getMockCreatureOutput() {
  return [
    {
      creature: "swe",
      output: "Received task: Fix authentication bug",
      timestamp: "10:31:03",
    },
    { creature: "swe", output: "⚙ bash: ls src/auth/", timestamp: "10:31:04" },
    { creature: "swe", output: "✓ bash: OK (5 files)", timestamp: "10:31:05" },
    {
      creature: "swe",
      output: "⚙ read: src/auth/middleware.py",
      timestamp: "10:31:06",
    },
    {
      creature: "swe",
      output: "✓ read: OK (142 lines)",
      timestamp: "10:31:08",
    },
    {
      creature: "swe",
      output: "Found issue at line 42: missing token.is_expired() check",
      timestamp: "10:31:10",
    },
    {
      creature: "swe",
      output: "⚙ edit: src/auth/middleware.py",
      timestamp: "10:31:12",
    },
    { creature: "swe", output: "✓ edit: OK", timestamp: "10:31:13" },
    {
      creature: "swe",
      output: "Sending fix for review...",
      timestamp: "10:31:15",
    },
  ];
}

/** @returns {{ channel: string, sender: string, content: string, timestamp: string }[]} */
export function getMockChannelMessages() {
  return [
    {
      channel: "tasks",
      sender: "root",
      content: "Fix the authentication bug in src/auth/middleware.py",
      timestamp: "10:31:02",
    },
    {
      channel: "review",
      sender: "swe",
      content:
        "Please review: Added token expiry validation in middleware.py line 42",
      timestamp: "10:31:15",
    },
    {
      channel: "feedback",
      sender: "reviewer",
      content: "LGTM - expiry check is correct. Consider adding a test case.",
      timestamp: "10:32:05",
    },
    {
      channel: "results",
      sender: "reviewer",
      content: "Approved: auth middleware fix with token expiry validation",
      timestamp: "10:32:10",
    },
    {
      channel: "team_chat",
      sender: "swe",
      content:
        "Starting work on the auth fix. The middleware.py file has a clear gap at line 42.",
      timestamp: "10:31:04",
    },
    {
      channel: "team_chat",
      sender: "reviewer",
      content: "Sounds good. Make sure to check the token refresh path too.",
      timestamp: "10:31:06",
    },
    {
      channel: "team_chat",
      sender: "swe",
      content: "Good point, I'll check both validate() and refresh() paths.",
      timestamp: "10:31:08",
    },
    {
      channel: "team_chat",
      sender: "swe",
      content:
        "Fix submitted to review channel. Two changes: expiry check + refresh validation.",
      timestamp: "10:31:16",
    },
    {
      channel: "team_chat",
      sender: "reviewer",
      content: "Reviewing now. The fix looks clean.",
      timestamp: "10:32:00",
    },
  ];
}

/** @returns {{ creature: string, output: string, timestamp: string }[]} */
export function getMockReviewerOutput() {
  return [
    {
      creature: "reviewer",
      output: "Received code review request",
      timestamp: "10:31:16",
    },
    {
      creature: "reviewer",
      output: "⚙ read: src/auth/middleware.py",
      timestamp: "10:31:18",
    },
    {
      creature: "reviewer",
      output: "✓ read: OK (142 lines)",
      timestamp: "10:31:20",
    },
    {
      creature: "reviewer",
      output: "Checking token validation logic...",
      timestamp: "10:31:22",
    },
    {
      creature: "reviewer",
      output: "Expiry check at line 42 looks correct",
      timestamp: "10:31:30",
    },
    {
      creature: "reviewer",
      output: "Refresh path also handled properly",
      timestamp: "10:31:45",
    },
    {
      creature: "reviewer",
      output: "Approved. Sending to results channel.",
      timestamp: "10:32:05",
    },
  ];
}
