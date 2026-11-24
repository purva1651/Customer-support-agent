import asyncio

import chainlit as cl
from chainlit.input_widget import Select, TextInput

from frontend.api_client import APIError, SupportAPI


@cl.on_chat_start
async def on_chat_start() -> None:
    settings = await cl.ChatSettings(
        [
            TextInput(
                id="customer_id",
                label="Demo customer ID",
                initial="C001",
                description="Use C001 or C002 for the seeded demo accounts.",
            ),
            Select(
                id="language",
                label="Reply language",
                values=["English", "Hindi", "Gujarati"],
                initial_index=0,
            ),
        ]
    ).send()
    cl.user_session.set("customer_id", settings.get("customer_id", "C001"))
    cl.user_session.set("language", settings.get("language", "English"))
    cl.user_session.set("session_id", cl.context.session.id)
    await cl.Message(
        content="Hi! Ask a question about your booking or our ticket policies."
    ).send()


@cl.on_settings_update
async def on_settings_update(settings: dict[str, str]) -> None:
    if settings.get("customer_id"):
        cl.user_session.set("customer_id", settings["customer_id"].strip())
    if settings.get("language") in {"English", "Hindi", "Gujarati"}:
        cl.user_session.set("language", settings["language"])


@cl.on_message
async def on_message(message: cl.Message) -> None:
    api = SupportAPI()
    try:
        response = await asyncio.to_thread(
            api.chat,
            customer_id=cl.user_session.get("customer_id", "C001"),
            session_id=cl.user_session.get("session_id", cl.context.session.id),
            message=message.content,
            language=cl.user_session.get("language", "English"),
        )
    except APIError as exc:
        await cl.Message(content=f"I couldn't contact the support service: {exc}").send()
        return
    finally:
        api.close()

    for call in response.get("tool_calls", []):
        async with cl.Step(name=call.get("name", "Tool")) as step:
            step.output = call.get("summary", "Completed")

    content = response.get("reply", "")
    sources = response.get("sources", [])
    if sources:
        content += "\n\n**Sources**\n" + "\n".join(
            f"- [{source['title']}]({source['url']})" for source in sources
        )
    if response.get("escalated"):
        content = f"🚩 **Escalated to a support specialist**\n\n{content}"
        summary = response.get("escalation_summary")
        if summary:
            content += f"\n\n**Handoff summary:** {summary}"

    actions = []
    pending = response.get("pending_action")
    if pending:
        content += f"\n\n**Approval needed:** {pending['description']}"
        action_id = pending["action_id"]
        actions = [
            cl.Action(
                name="approve_action",
                label="Yes, approve",
                payload={"action_id": action_id, "approved": True},
            ),
            cl.Action(
                name="approve_action",
                label="No, cancel",
                payload={"action_id": action_id, "approved": False},
            ),
        ]
    await cl.Message(content=content, actions=actions or None).send()


@cl.action_callback("approve_action")
async def approve_action(action: cl.Action) -> None:
    api = SupportAPI()
    try:
        result = await asyncio.to_thread(
            api.approve, action.payload["action_id"], action.payload["approved"]
        )
        content = result.get("reply", "Your choice has been recorded.")
    except APIError as exc:
        content = f"I couldn't submit that approval: {exc}"
    finally:
        api.close()
    await cl.Message(content=content).send()
