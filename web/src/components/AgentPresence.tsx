export type AgentActivity = "idle" | "thinking" | "streaming" | "offline" | "error";
export type AgentSource = "report" | "ask";
export type AgentSignal = (source: AgentSource, activity: AgentActivity) => void;

const LABELS: Record<AgentActivity, string> = {
  idle: "Agent idle",
  thinking: "Agent thinking",
  streaming: "Agent streaming",
  offline: "Agent offline",
  error: "Agent error",
};

export function AgentPresence({ state }: { state: AgentActivity }) {
  return (
    <span className="agent-presence" data-state={state} role="img" aria-label={LABELS[state]}>
      <span className="agent-orb" />
    </span>
  );
}
