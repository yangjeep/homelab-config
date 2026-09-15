"""Native Bolt middleware; Slack credentials select the Hermes profile."""
import os
from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol, assert_never

from pydantic import JsonValue, ValidationError
from slack_bolt.response import BoltResponse

from .policy import COS, Decision, Envelope, Identities, decision, load_identities


class SlackAdapter(Protocol):
    _team_bot_user_ids: Mapping[str, str]


Middleware = Callable[..., Awaitable[BoltResponse]]


class NativeSlack(Protocol):
    def use(self, *args: Middleware) -> None: ...


class PluginContext(Protocol):
    def register_platform_handler(
        self, platform: str, factory: Callable[[NativeSlack, SlackAdapter], None],
    ) -> None: ...


def install(native: NativeSlack, adapter: SlackAdapter, identities: Identities) -> None:
    """Register a real coroutine with Bolt's documented `next` injection name."""
    role = os.environ.get("HERMES_PROFILE", "")

    async def ingress(
        body: dict[str, JsonValue], next: Callable[[], Awaitable[BoltResponse]],
    ) -> BoltResponse:
        identity = identities.roles.get(role)
        if identity is None or adapter._team_bot_user_ids.get(identities.team_id) != identity.bot_user_id:
            return BoltResponse(status=200)
        try:
            payload = Envelope.model_validate(body)
        except ValidationError:
            return BoltResponse(status=200)
        match decision(payload, role, identities):
            case Decision.BLOCK:
                return BoltResponse(status=200)
            case Decision.COORDINATE:
                event = body.get("event")
                # Parsed above; mutate the same dict native Bolt listeners receive.
                if isinstance(event, dict):
                    event["_leaselab_original_text"] = payload.event.text
                    event["text"] = f"<@{identities.roles[COS].bot_user_id}> {payload.event.text}"
                return await next()
            case Decision.DIRECT:
                return await next()
            case unreachable:
                assert_never(unreachable)

    native.use(ingress)


def register(ctx: PluginContext) -> None:
    """Refuse gateway startup when the root-owned identity map is invalid."""
    identities = load_identities()

    def factory(native: NativeSlack, adapter: SlackAdapter) -> None:
        install(native, adapter, identities)

    ctx.register_platform_handler("slack", factory)
