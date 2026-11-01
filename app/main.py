"""Command-line entry point for the local MVP."""

from __future__ import annotations

import argparse
import asyncio
import json

from app.ai.azure_client import AzureOpenAIClient
from app.config import Settings
from app.database.repository import Repository
from app.orchestrator.engine import Orchestrator
from app.schemas.models import Approval, Project, ProjectRequest
from app.web.dashboard import serve_dashboard


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-dev-team")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="create a project")
    create.add_argument("name")
    create.add_argument("requirement")
    plan = sub.add_parser("plan", help="generate an Azure OpenAI plan")
    plan.add_argument("project_id")
    approve = sub.add_parser("request-approval", help="request human plan approval")
    approve.add_argument("project_id")
    decide = sub.add_parser("decide", help="decide a pending approval")
    decide.add_argument("approval_id")
    decide.add_argument("approver_id")
    decide.add_argument("decision", choices=("approve", "reject"))
    status = sub.add_parser("status", help="show project state")
    status.add_argument("project_id")
    run = sub.add_parser("run", help="run approved development tasks")
    run.add_argument("project_id")
    integration_request = sub.add_parser("request-integration", help="request merge approval")
    integration_request.add_argument("project_id")
    integrate = sub.add_parser("integrate", help="merge approved worktrees")
    integrate.add_argument("project_id")
    qa = sub.add_parser("qa", help="run final Docker-backed QA")
    qa.add_argument("project_id")
    browser_qa = sub.add_parser("browser-qa", help="run isolated Playwright QA")
    browser_qa.add_argument("project_id")
    browser_qa.add_argument("--url", default="http://127.0.0.1:8000/")
    browser_qa.add_argument("--start-command", nargs="+", required=True)
    deliver = sub.add_parser("deliver", help="publish the final delivery report")
    deliver.add_argument("project_id")
    recover = sub.add_parser("recover", help="load latest checkpoint")
    recover.add_argument("project_id")
    sub.add_parser("dashboard", help="start the local authenticated dashboard")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = Settings.from_env()
    settings.ensure_directories()
    repository = Repository(settings.database_path)
    if args.command == "dashboard":
        serve_dashboard(settings, repository)
        return
    if args.command == "create":
        orchestrator = Orchestrator(settings, repository)
        project = orchestrator.create_project(
            ProjectRequest(name=args.name, requirement=args.requirement)
        )
        print(json.dumps(project.model_dump(mode="json"), indent=2))
        return
    loaded_project = repository.get_project(args.project_id if hasattr(args, "project_id") else "")
    if loaded_project is None and args.command != "decide":
        raise SystemExit("project not found")
    client = (
        None
        if args.command in {"status", "request-approval", "decide", "recover", "request-integration",
                            "integrate", "qa", "browser-qa", "deliver"}
        else AzureOpenAIClient(settings)
    )
    orchestrator = Orchestrator(settings, repository, client)
    if args.command == "plan":
        print(
            json.dumps(
                asyncio.run(orchestrator.generate_plan(args.project_id)).model_dump(mode="json"),
                indent=2,
            )
        )
    elif args.command == "request-approval":
        print(orchestrator.request_plan_approval(args.project_id))
    elif args.command == "decide":
        approval = repository.get_approval(args.approval_id)
        if approval is None:
            raise SystemExit("approval not found")
        decided: Approval | Project
        if approval.action == "approve_plan":
            decided = orchestrator.approve_plan(
                args.approval_id, args.approver_id, args.decision == "approve"
            )
        else:
            decided = orchestrator.approvals.decide(args.approval_id, args.approver_id,
                                                    args.decision == "approve")
        print(
            json.dumps(
                decided.model_dump(mode="json"),
                indent=2,
            )
        )
    elif args.command == "run":
        asyncio.run(orchestrator.run_development(args.project_id))
        print("development complete")
    elif args.command == "request-integration":
        print(orchestrator.request_integration(args.project_id))
    elif args.command == "integrate":
        print(json.dumps(orchestrator.integrate(args.project_id), indent=2))
    elif args.command == "qa":
        print(json.dumps(orchestrator.run_final_qa(args.project_id).model_dump(mode="json"), indent=2))
    elif args.command == "browser-qa":
        print(json.dumps(orchestrator.run_browser_qa(args.project_id, args.start_command, args.url).model_dump(mode="json"), indent=2))
    elif args.command == "deliver":
        print(orchestrator.deliver(args.project_id))
    elif args.command == "recover":
        print(json.dumps(orchestrator.recover(args.project_id), indent=2, default=str))
    elif args.command == "status":
        if loaded_project is None:
            raise SystemExit("project not found")
        print(
            json.dumps(
                {
                    "project": loaded_project.model_dump(mode="json"),
                    "tasks": [
                        task.model_dump(mode="json")
                        for task in repository.list_tasks(args.project_id)
                    ],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
