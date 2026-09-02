import json
from typing import Annotated, Any, TypedDict
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from voxforge.config import Settings
from voxforge.core.domain.agents import (
    CRITIC_PROMPT,
    EXECUTOR_PROMPT,
    PLANNER_PROMPT,
    SAFETY_PROMPT,
)

if False:  # TYPE_CHECKING
    pass


class OrchestratorState(TypedDict):
    messages: list[dict]
    user_input: str
    plan: str
    draft_response: str
    safety_passed: bool
    safety_reason: str
    critic_approved: bool
    critic_feedback: str
    final_response: str
    iteration: int
    session_id: str | None
    org_id: str | None
    caller_scopes: list[str]
    agent_trace: Annotated[list[dict], lambda a, b: a + b]
    tool_calls: Annotated[list[dict], lambda a, b: a + b]


def _to_lc_messages(messages: list[dict]) -> list[BaseMessage]:
    result: list[BaseMessage] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            result.append(SystemMessage(content=content))
        elif role == "assistant":
            result.append(AIMessage(content=content))
        else:
            result.append(HumanMessage(content=content))
    return result


def _trace(agent: str, status: str, summary: str) -> list[dict]:
    return [{"agent": agent, "status": status, "summary": summary}]


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _parse_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def build_agent_graph(settings: Settings, tool_router: Any | None = None):
    planner_llm = ChatOpenAI(model=settings.planner_model, api_key=settings.openai_api_key)
    executor_llm = ChatOpenAI(model=settings.executor_model, api_key=settings.openai_api_key)
    critic_llm = ChatOpenAI(model=settings.critic_model, api_key=settings.openai_api_key)
    safety_llm = ChatOpenAI(model=settings.safety_model, api_key=settings.openai_api_key)

    async def planner(state: OrchestratorState) -> dict:
        history = _to_lc_messages(state["messages"])
        prompt = (
            f"{PLANNER_PROMPT}\n\nUser message: {state['user_input']}\n"
            f"Iteration: {state['iteration']}"
        )
        if state.get("critic_feedback"):
            prompt += f"\nCritic feedback to address: {state['critic_feedback']}"
        response = await planner_llm.ainvoke(history + [HumanMessage(content=prompt)])
        plan = response.content if isinstance(response.content, str) else str(response.content)
        return {
            "plan": plan,
            "agent_trace": _trace("planner", "completed", plan[:200]),
        }

    async def safety(state: OrchestratorState) -> dict:
        prompt = f"{SAFETY_PROMPT}\n\nUser: {state['user_input']}\nPlan: {state.get('plan', '')}"
        response = await safety_llm.ainvoke([HumanMessage(content=prompt)])
        content = response.content if isinstance(response.content, str) else str(response.content)
        parsed = _parse_json(content)
        passed = bool(parsed.get("passed", True))
        reason = str(parsed.get("reason", ""))
        status = "completed" if passed else "blocked"
        result: dict = {
            "safety_passed": passed,
            "safety_reason": reason,
            "agent_trace": _trace("safety", status, reason or "passed"),
        }
        if not passed:
            result["final_response"] = "I'm sorry, but I can't help with that request."
        return result

    async def executor(state: OrchestratorState) -> dict:
        history = _to_lc_messages(state["messages"])
        tool_list = ""
        if tool_router and settings.tools_enabled:
            tools = tool_router.list_tools()
            if tools:
                tool_list = "\n\nAvailable tools:\n" + "\n".join(
                    f"- {t.name}: {t.description}" for t in tools
                )

        prompt = (
            f"{EXECUTOR_PROMPT}{tool_list}\n\nPlan:\n{state.get('plan', '')}\n\n"
            f"User message: {state['user_input']}"
        )
        lc_messages: list[BaseMessage] = history + [HumanMessage(content=prompt)]
        tool_trace: list[dict] = []
        recorded_calls: list[dict] = []
        org_id = _parse_uuid(state.get("org_id"))
        session_id = _parse_uuid(state.get("session_id"))

        lc_tools = (
            tool_router.get_langchain_tools() if tool_router and settings.tools_enabled else []
        )
        llm = executor_llm.bind_tools(lc_tools) if lc_tools else executor_llm

        draft = ""
        response: AIMessage | None = None
        for _ in range(settings.max_tool_iterations + 1):
            response = await llm.ainvoke(lc_messages)
            tool_calls = getattr(response, "tool_calls", None) or []
            if not tool_calls:
                draft = (
                    response.content if isinstance(response.content, str) else str(response.content)
                )
                break

            lc_messages.append(response)
            for tc in tool_calls:
                tool_name = tc["name"]
                args = tc.get("args", {})
                tool_result = await tool_router.execute(
                    tool_name,
                    args,
                    org_id=org_id,
                    session_id=session_id,
                    caller_scopes=state.get("caller_scopes", []),
                )
                output = tool_result.output or tool_result.error or ""
                recorded_calls.append(
                    {
                        "tool": tool_name,
                        "arguments": args,
                        "status": tool_result.status.value,
                        "output": output[:500],
                    }
                )
                tool_trace.extend(
                    _trace("tool", tool_result.status.value, f"{tool_name}: {output[:120]}")
                )
                lc_messages.append(ToolMessage(content=output, tool_call_id=tc["id"]))
        else:
            if response is not None:
                draft = (
                    response.content if isinstance(response.content, str) else str(response.content)
                )

        return {
            "draft_response": draft,
            "agent_trace": _trace("executor", "completed", draft[:200]) + tool_trace,
            "tool_calls": recorded_calls,
        }

    async def critic(state: OrchestratorState) -> dict:
        prompt = (
            f"{CRITIC_PROMPT}\n\nDraft response:\n{state.get('draft_response', '')}\n\n"
            f"User message: {state['user_input']}"
        )
        response = await critic_llm.ainvoke([HumanMessage(content=prompt)])
        content = response.content if isinstance(response.content, str) else str(response.content)
        parsed = _parse_json(content)
        approved = bool(parsed.get("approved", True))
        feedback = str(parsed.get("feedback", ""))
        return {
            "critic_approved": approved,
            "critic_feedback": feedback,
            "iteration": state["iteration"] + (0 if approved else 1),
            "agent_trace": _trace(
                "critic",
                "completed" if approved else "revised",
                feedback[:200] if feedback else "approved",
            ),
        }

    async def coordinator(state: OrchestratorState) -> dict:
        if state.get("final_response"):
            return {
                "agent_trace": _trace("coordinator", "blocked", state.get("safety_reason", "")),
            }
        final = state.get("draft_response", "")
        return {
            "final_response": final,
            "agent_trace": _trace("coordinator", "completed", final[:200]),
        }

    def route_after_safety(state: OrchestratorState) -> str:
        return "executor" if state.get("safety_passed", True) else "coordinator"

    def route_after_critic(state: OrchestratorState) -> str:
        if state.get("critic_approved", True):
            return "coordinator"
        if state.get("iteration", 0) >= settings.max_agent_iterations:
            return "coordinator"
        return "planner"

    graph = StateGraph(OrchestratorState)
    graph.add_node("planner", planner)
    graph.add_node("safety", safety)
    graph.add_node("executor", executor)
    graph.add_node("critic", critic)
    graph.add_node("coordinator", coordinator)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "safety")
    graph.add_conditional_edges("safety", route_after_safety, ["executor", "coordinator"])
    graph.add_edge("executor", "critic")
    graph.add_conditional_edges("critic", route_after_critic, ["coordinator", "planner"])
    graph.add_edge("coordinator", END)

    return graph.compile()


def build_mock_agent_graph(
    settings: Settings, tool_router: Any | None = None, llm: Any | None = None
):
    """Deterministic planner → safety → executor → critic graph for mock LLM demos.

    Still executes real tools so /demo can show an agent trace without OpenAI.
    """

    async def planner(state: OrchestratorState) -> dict:
        plan = "Look up knowledge, then answer from retrieved policy."
        return {"plan": plan, "agent_trace": _trace("planner", "completed", plan)}

    async def safety(state: OrchestratorState) -> dict:
        return {
            "safety_passed": True,
            "safety_reason": "passed",
            "agent_trace": _trace("safety", "completed", "passed"),
        }

    async def executor(state: OrchestratorState) -> dict:
        from voxforge.core.domain.entities import MessageRole

        recorded_calls: list[dict] = []
        tool_trace: list[dict] = []
        org_id = _parse_uuid(state.get("org_id"))
        session_id = _parse_uuid(state.get("session_id"))
        if tool_router and settings.tools_enabled:
            names = {item.name for item in tool_router.list_tools()}
            if "knowledge_base_lookup" in names:
                tool_result = await tool_router.execute(
                    "knowledge_base_lookup",
                    {"query": state["user_input"]},
                    org_id=org_id,
                    session_id=session_id,
                    caller_scopes=state.get("caller_scopes", []),
                )
                output = tool_result.output or tool_result.error or ""
                recorded_calls.append(
                    {
                        "tool": "knowledge_base_lookup",
                        "arguments": {"query": state["user_input"]},
                        "status": tool_result.status.value,
                        "output": output[:500],
                    }
                )
                tool_trace.extend(
                    _trace(
                        "tool",
                        tool_result.status.value,
                        f"knowledge_base_lookup: {output[:120]}",
                    )
                )

        draft = ""
        if llm is not None:

            class _Msg:
                def __init__(self, role: MessageRole, content: str) -> None:
                    self.role = role
                    self.content = content

            history = [
                _Msg(MessageRole(msg.get("role", "user")), str(msg.get("content", "")))
                for msg in state.get("messages", [])
            ]
            if not history:
                history = [_Msg(MessageRole.USER, state["user_input"])]
            parts: list[str] = []
            async for event in llm.generate_stream(history, model=settings.default_llm_model):
                if event.text:
                    parts.append(event.text)
            draft = "".join(parts).strip()
        if not draft:
            draft = "I looked that up and can help with the next step."
        return {
            "draft_response": draft,
            "agent_trace": _trace("executor", "completed", draft[:200]) + tool_trace,
            "tool_calls": recorded_calls,
        }

    async def critic(state: OrchestratorState) -> dict:
        return {
            "critic_approved": True,
            "critic_feedback": "approved",
            "iteration": state["iteration"],
            "agent_trace": _trace("critic", "completed", "approved"),
        }

    async def coordinator(state: OrchestratorState) -> dict:
        final = state.get("draft_response", "")
        return {
            "final_response": final,
            "agent_trace": _trace("coordinator", "completed", final[:200]),
        }

    graph = StateGraph(OrchestratorState)
    graph.add_node("planner", planner)
    graph.add_node("safety", safety)
    graph.add_node("executor", executor)
    graph.add_node("critic", critic)
    graph.add_node("coordinator", coordinator)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "safety")
    graph.add_edge("safety", "executor")
    graph.add_edge("executor", "critic")
    graph.add_edge("critic", "coordinator")
    graph.add_edge("coordinator", END)
    return graph.compile()
