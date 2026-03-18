from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from andino.config import AgentConfig
from andino.task_executor import TaskExecutor, TaskState, TaskStatus


class TaskRequest(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    prompt: str
    session_id: str | None = None


class TaskAccepted(BaseModel):
    task_id: str
    status: TaskState = TaskState.queued


class InterruptResponse(BaseModel):
    interrupt_id: str
    response: str


def create_app(config: AgentConfig, executor: TaskExecutor | None = None) -> FastAPI:
    """Create a FastAPI application for a standalone Andino agent."""
    if executor is None:
        executor = TaskExecutor(config)
    start_time = time.monotonic()

    app = FastAPI(
        title=f"Andino Agent: {config.name}",
        version=config.version,
        description=config.description,
    )

    @app.post("/task", status_code=202, response_model=TaskAccepted)
    async def submit_task(request: TaskRequest) -> TaskAccepted:
        try:
            status = await executor.submit(request.task_id, request.prompt, request.session_id)
        except ValueError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        return TaskAccepted(task_id=status.task_id)

    @app.get("/task/{task_id}", response_model=TaskStatus)
    async def get_task(task_id: str) -> TaskStatus:
        status = executor.get_status(task_id)
        if not status:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return status

    @app.post("/task/{task_id}/respond")
    async def respond_to_task(task_id: str, body: InterruptResponse) -> dict:
        task = executor.get_status(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        if task.status != TaskState.interrupted:
            raise HTTPException(
                status_code=409,
                detail=f"Task {task_id} is not interrupted (status: {task.status})",
            )
        responses = [
            {"interruptResponse": {"interruptId": body.interrupt_id, "response": body.response}}
        ]
        if not executor.respond_to_interrupt(task_id, responses):
            raise HTTPException(status_code=409, detail="No pending interrupt for this task")
        return {"task_id": task_id, "status": "resumed"}

    @app.get("/tasks", response_model=list[TaskStatus])
    async def list_tasks() -> list[TaskStatus]:
        return executor.list_tasks()

    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "agent_name": config.name,
            "running_tasks": executor.running_count,
            "uptime_seconds": round(time.monotonic() - start_time, 1),
        }

    @app.get("/info")
    async def info() -> dict:
        return {
            "name": config.name,
            "version": config.version,
            "description": config.description,
            "model": {
                "provider": config.model.provider,
                "model_id": config.model.model_id,
            },
            "tools": config.tools,
            "max_concurrent_tasks": config.limits.max_concurrent_tasks,
            "task_timeout_seconds": config.limits.task_timeout_seconds,
        }

    return app
