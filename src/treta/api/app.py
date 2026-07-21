import asyncio
import os
import re
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, cast
from uuid import uuid4

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from treta import __version__
from treta.adapters.durable import JsonlEventStore
from treta.adapters.memory import (
    EntityNotFoundError,
    LocalHeaderIdentityProvider,
    authorize,
)
from treta.application.control_plane import (
    DEFAULT_TENANT_ID,
    ApplicationConflictError,
    ControlPlaneService,
)
from treta.domain.models import FailureType, Position, to_primitive
from treta.domain.state_machines import InvalidTransition
from treta.ports.interfaces import AuthenticationError, AuthorizationError, Principal

MAX_REQUEST_BYTES = 64 * 1024
RATE_LIMIT_PER_MINUTE = 600
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PositionRequest(StrictRequest):
    latitude_deg: float = Field(ge=-90, le=90)
    longitude_deg: float = Field(ge=-180, le=180)


class MissionCreateRequest(StrictRequest):
    origin: PositionRequest
    destination: PositionRequest
    payload_kg: float = Field(gt=0, le=100)
    minimum_landing_reserve_percent: float = Field(ge=0, le=100)


class FailureRequest(StrictRequest):
    drone_id: str = Field(min_length=1, max_length=64)
    failure_type: FailureType
    severity: str = Field(pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    multiplier: float = Field(gt=0, le=100)


class StepRequest(StrictRequest):
    seconds: int = Field(default=1, ge=1, le=60)


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._requests: defaultdict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float) -> bool:
        window = self._requests[key]
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= RATE_LIMIT_PER_MINUTE:
            return False
        window.append(now)
        return True


def _problem(status: int, code: str, detail: str, request_id: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "detail": detail,
                "request_id": request_id,
            }
        },
    )


def create_app(service: ControlPlaneService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield

    application = FastAPI(
        title="Treta API",
        version=__version__,
        description="Simulation-only supervisory control plane. Not an airworthiness claim.",
        lifespan=lifespan,
    )
    if service is None:
        event_directory = Path(os.getenv("TRETA_EVENT_DIRECTORY", ".treta/events"))
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        event_path = event_directory / f"session-{timestamp}-{uuid4().hex[:8]}.jsonl"
        service = ControlPlaneService(event_store=JsonlEventStore(event_path))
    application.state.service = service
    application.state.identity = LocalHeaderIdentityProvider()
    application.state.rate_limiter = InMemoryRateLimiter()

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=[
            "Content-Type",
            "Idempotency-Key",
            "X-Request-ID",
            "X-Treta-Actor",
            "X-Treta-Role",
            "X-Treta-Tenant-ID",
        ],
    )

    @application.middleware("http")
    async def request_guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        supplied_request_id = request.headers.get("X-Request-ID")
        request_id = (
            supplied_request_id
            if supplied_request_id and REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
            else f"req-{uuid4()}"
        )
        request.state.request_id = request_id
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_REQUEST_BYTES:
                    return _problem(
                        413, "REQUEST_TOO_LARGE", "request body exceeds 65536 bytes", request_id
                    )
            except ValueError:
                return _problem(
                    400, "INVALID_CONTENT_LENGTH", "invalid Content-Length header", request_id
                )
        actor = (
            request.headers.get("X-Treta-Actor") or request.client.host
            if request.client
            else "unknown"
        )
        if not application.state.rate_limiter.allow(actor, time.monotonic()):
            return _problem(429, "RATE_LIMITED", "local request rate limit exceeded", request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @application.exception_handler(AuthenticationError)
    async def authentication_error(request: Request, error: AuthenticationError) -> JSONResponse:
        return _problem(401, "AUTHENTICATION_REQUIRED", str(error), request.state.request_id)

    @application.exception_handler(AuthorizationError)
    async def authorization_error(request: Request, error: AuthorizationError) -> JSONResponse:
        return _problem(403, "AUTHORIZATION_DENIED", str(error), request.state.request_id)

    @application.exception_handler(EntityNotFoundError)
    async def not_found(request: Request, error: EntityNotFoundError) -> JSONResponse:
        return _problem(404, "ENTITY_NOT_FOUND", str(error), request.state.request_id)

    @application.exception_handler(ApplicationConflictError)
    async def application_conflict(
        request: Request, error: ApplicationConflictError
    ) -> JSONResponse:
        return _problem(409, "STATE_CONFLICT", str(error), request.state.request_id)

    @application.exception_handler(InvalidTransition)
    async def transition_conflict(request: Request, error: InvalidTransition) -> JSONResponse:
        return _problem(409, "STATE_CONFLICT", str(error), request.state.request_id)

    @application.exception_handler(ValueError)
    async def invalid_value(request: Request, error: ValueError) -> JSONResponse:
        return _problem(422, "INVALID_INPUT", str(error), request.state.request_id)

    def current_principal(
        request: Request,
        actor_id: Annotated[str | None, Header(alias="X-Treta-Actor")] = None,
        tenant_id: Annotated[str | None, Header(alias="X-Treta-Tenant-ID")] = None,
        role: Annotated[str | None, Header(alias="X-Treta-Role")] = None,
    ) -> Principal:
        identity = cast(LocalHeaderIdentityProvider, request.app.state.identity)
        return identity.authenticate(actor_id, tenant_id, role)

    def idempotency_key(
        value: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    ) -> str:
        if value is None or not 1 <= len(value) <= 128:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "IDEMPOTENCY_KEY_REQUIRED",
                    "detail": "1-128 character key required",
                },
            )
        return value

    PrincipalDependency = Annotated[Principal, Depends(current_principal)]
    IdempotencyDependency = Annotated[str, Depends(idempotency_key)]

    def app_service() -> ControlPlaneService:
        return cast(ControlPlaneService, application.state.service)

    def read_service(principal: Principal) -> ControlPlaneService:
        authorize(principal, "read", DEFAULT_TENANT_ID)
        return app_service()

    @application.get("/api/v1/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "live"}

    @application.get("/api/v1/health/ready", tags=["health"])
    def ready() -> dict[str, str]:
        return {"status": "ready", "mode": "simulation-only"}

    @application.get("/api/v1/system/version", tags=["system"])
    def version() -> dict[str, str]:
        return {
            "version": __version__,
            "environment": "local",
            "physical_pilot": "disabled",
        }

    @application.get("/api/v1/fleets", tags=["fleet"])
    def fleets(principal: PrincipalDependency) -> list[dict[str, Any]]:
        service_instance = read_service(principal)
        drones = service_instance.repository.list_drones(DEFAULT_TENANT_ID)
        return [
            {
                "fleet_id": "fleet-demo",
                "tenant_id": DEFAULT_TENANT_ID,
                "name": "Synthetic demo fleet",
                "region": "synthetic-test-range",
                "drone_count": len(drones),
            }
        ]

    @application.get("/api/v1/drones", tags=["fleet"])
    def drones(principal: PrincipalDependency) -> Any:
        return to_primitive(read_service(principal).repository.list_drones(DEFAULT_TENANT_ID))

    @application.get("/api/v1/drones/{drone_id}", tags=["fleet"])
    def drone(drone_id: str, principal: PrincipalDependency) -> Any:
        return to_primitive(
            read_service(principal).repository.get_drone(DEFAULT_TENANT_ID, drone_id)
        )

    @application.get("/api/v1/drones/{drone_id}/telemetry/latest", tags=["telemetry"])
    def telemetry(drone_id: str, principal: PrincipalDependency) -> Any:
        service_instance = read_service(principal)
        service_instance.repository.get_drone(DEFAULT_TENANT_ID, drone_id)
        return to_primitive(service_instance.simulator.latest_telemetry(drone_id))

    @application.get("/api/v1/missions", tags=["missions"])
    def missions(principal: PrincipalDependency) -> Any:
        return to_primitive(read_service(principal).repository.list_missions(DEFAULT_TENANT_ID))

    @application.post("/api/v1/missions", status_code=201, tags=["missions"])
    def create_mission_endpoint(
        body: MissionCreateRequest,
        principal: PrincipalDependency,
        key: IdempotencyDependency,
    ) -> Any:
        mission = app_service().create_mission(
            principal,
            origin=Position(body.origin.latitude_deg, body.origin.longitude_deg),
            destination=Position(body.destination.latitude_deg, body.destination.longitude_deg),
            payload_kg=body.payload_kg,
            minimum_landing_reserve_percent=body.minimum_landing_reserve_percent,
            idempotency_key=key,
        )
        return to_primitive(mission)

    @application.get("/api/v1/missions/{mission_id}", tags=["missions"])
    def mission(mission_id: str, principal: PrincipalDependency) -> Any:
        return to_primitive(
            read_service(principal).repository.get_mission(DEFAULT_TENANT_ID, mission_id)
        )

    @application.post("/api/v1/missions/{mission_id}/evaluate", tags=["missions"])
    def evaluate_mission(
        mission_id: str,
        principal: PrincipalDependency,
        _: IdempotencyDependency,
    ) -> Any:
        return to_primitive(app_service().evaluate_mission(principal, mission_id))

    @application.post("/api/v1/missions/{mission_id}/assign", tags=["missions"])
    def assign_mission(
        mission_id: str,
        principal: PrincipalDependency,
        key: IdempotencyDependency,
    ) -> Any:
        return to_primitive(app_service().assign_mission(principal, mission_id, key))

    @application.post("/api/v1/missions/{mission_id}/start", tags=["missions"])
    def start_mission(
        mission_id: str,
        principal: PrincipalDependency,
        key: IdempotencyDependency,
    ) -> Any:
        return to_primitive(app_service().start_mission(principal, mission_id, key))

    @application.get("/api/v1/missions/{mission_id}/events", tags=["events"])
    def mission_events(mission_id: str, principal: PrincipalDependency) -> Any:
        service_instance = read_service(principal)
        service_instance.repository.get_mission(DEFAULT_TENANT_ID, mission_id)
        return to_primitive(
            [
                event
                for event in service_instance.events(limit=500)
                if event.correlation_id == mission_id or event.aggregate_id == mission_id
            ]
        )

    @application.get("/api/v1/missions/{mission_id}/replay", tags=["replay"])
    def replay(mission_id: str, principal: PrincipalDependency) -> Any:
        service_instance = read_service(principal)
        service_instance.repository.get_mission(DEFAULT_TENANT_ID, mission_id)
        return to_primitive(service_instance.replay())

    @application.post("/api/v1/simulation/start", tags=["simulation"])
    def start_simulation(
        principal: PrincipalDependency, _: IdempotencyDependency
    ) -> dict[str, Any]:
        return app_service().start_simulation(principal)

    @application.post("/api/v1/simulation/pause", tags=["simulation"])
    def pause_simulation(
        principal: PrincipalDependency, _: IdempotencyDependency
    ) -> dict[str, Any]:
        return app_service().pause_simulation(principal)

    @application.post("/api/v1/simulation/step", tags=["simulation"])
    def step_simulation(
        body: StepRequest,
        principal: PrincipalDependency,
        _: IdempotencyDependency,
    ) -> dict[str, Any]:
        return app_service().step(principal, body.seconds)

    @application.post("/api/v1/simulation/failures", status_code=201, tags=["simulation"])
    def inject_failure(
        body: FailureRequest,
        principal: PrincipalDependency,
        key: IdempotencyDependency,
    ) -> dict[str, Any]:
        return app_service().inject_failure(
            principal,
            drone_id=body.drone_id,
            failure_type=body.failure_type,
            severity=body.severity,
            multiplier=body.multiplier,
            idempotency_key=key,
        )

    @application.get("/api/v1/simulation/status", tags=["simulation"])
    def simulation_status(principal: PrincipalDependency) -> dict[str, Any]:
        return read_service(principal).status()

    @application.get("/api/v1/incidents", tags=["incidents"])
    def incidents(principal: PrincipalDependency) -> Any:
        return to_primitive(read_service(principal).repository.list_incidents(DEFAULT_TENANT_ID))

    @application.get("/api/v1/incidents/{incident_id}", tags=["incidents"])
    def incident(incident_id: str, principal: PrincipalDependency) -> Any:
        service_instance = read_service(principal)
        incidents_by_id = {
            item.incident_id: item
            for item in service_instance.repository.list_incidents(DEFAULT_TENANT_ID)
        }
        if incident_id not in incidents_by_id:
            raise EntityNotFoundError(f"incident {incident_id!r} was not found")
        return to_primitive(incidents_by_id[incident_id])

    @application.get("/api/v1/events", tags=["events"])
    def events(
        principal: PrincipalDependency,
        after: str | None = Query(default=None, max_length=64),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> Any:
        return to_primitive(read_service(principal).events(after, limit))

    @application.get("/api/v1/safety-decisions", tags=["safety"])
    def safety_decisions(principal: PrincipalDependency) -> Any:
        service_instance = read_service(principal)
        return to_primitive(
            [
                event
                for event in service_instance.events(limit=500)
                if event.event_type.startswith("safety.")
            ]
        )

    @application.websocket("/api/v1/stream")
    async def stream(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            identity = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
            if not isinstance(identity, dict):
                raise AuthenticationError("stream identity message must be an object")
            principal = application.state.identity.authenticate(
                identity.get("actor_id"), identity.get("tenant_id"), identity.get("role")
            )
            authorize(principal, "read", DEFAULT_TENANT_ID)
            while True:
                await websocket.send_json(to_primitive(app_service().snapshot()))
                await asyncio.sleep(1.0)
        except (AuthenticationError, AuthorizationError) as error:
            await websocket.send_json(
                {"error": {"code": "AUTHORIZATION_DENIED", "detail": str(error)}}
            )
            await websocket.close(code=1008)
        except (TimeoutError, WebSocketDisconnect):
            return

    return application


app = create_app()
