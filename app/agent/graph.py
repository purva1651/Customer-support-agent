from typing import Any, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from app.agent.nodes import AgentServices, create_nodes
from app.agent.state import AgentState


def build_agent_graph(
    services: AgentServices, checkpointer: BaseCheckpointSaver
) -> Any:
    nodes = create_nodes(services)
    graph = StateGraph(AgentState)
    for name, node in nodes.items():
        graph.add_node(name, node)

    graph.set_entry_point("guardrails")
    graph.add_edge("guardrails", "router")
    graph.add_conditional_edges(
        "router",
        _route_by_intent,
        {
            "answer": "answer",
            "act": "act",
            "complaint": "complaint",
            "small_talk": "small_talk",
        },
    )
    for node_name in ("answer", "act", "complaint", "small_talk"):
        graph.add_conditional_edges(
            node_name,
            _route_after_work,
            {"escalate": "escalate", "respond": "respond"},
        )
    graph.add_edge("escalate", "respond")
    graph.add_edge("respond", END)
    return graph.compile(checkpointer=checkpointer)


def _route_by_intent(
    state: AgentState,
) -> Literal["answer", "act", "complaint", "small_talk"]:
    if state.get("intent") == "complaint" or state.get("negative_sentiment", False):
        return "complaint"
    intent = state.get("intent")
    if intent == "action":
        return "act"
    if intent == "small_talk":
        return "small_talk"
    return "answer"


def _route_after_work(state: AgentState) -> Literal["escalate", "respond"]:
    return "escalate" if state.get("escalation_reason") else "respond"
