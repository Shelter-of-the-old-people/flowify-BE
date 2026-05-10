from app.models.requests import WorkflowExecuteRequest
from app.models.workflow import WorkflowDefinition


def test_workflow_definition_accepts_schedule_trigger_payload():
    workflow = WorkflowDefinition.model_validate(
        {
            "id": "wf_schedule",
            "name": "Scheduled workflow",
            "userId": "usr_1",
            "nodes": [],
            "edges": [],
            "trigger": {
                "type": "schedule",
                "config": {
                    "schedule_mode": "interval",
                    "cron": "0 0 */4 * * *",
                    "timezone": "Asia/Seoul",
                    "interval_hours": 4,
                    "skip_if_running": True,
                },
            },
            "active": True,
            "template": False,
        }
    )

    assert workflow.trigger is not None
    assert workflow.trigger.type == "schedule"
    assert workflow.trigger.config["timezone"] == "Asia/Seoul"
    assert workflow.trigger.config["interval_hours"] == 4


def test_workflow_definition_allows_null_trigger_for_legacy_payloads():
    workflow = WorkflowDefinition.model_validate(
        {
            "id": "wf_manual",
            "name": "Manual workflow",
            "userId": "usr_1",
            "nodes": [],
            "edges": [],
            "trigger": None,
            "active": True,
            "template": False,
        }
    )

    assert workflow.trigger is None


def test_workflow_execute_request_accepts_schedule_trigger_without_special_handling():
    request = WorkflowExecuteRequest.model_validate(
        {
            "workflow": {
                "id": "wf_schedule",
                "name": "Scheduled workflow",
                "userId": "usr_1",
                "nodes": [],
                "edges": [],
                "trigger": {
                    "type": "schedule",
                    "config": {
                        "schedule_mode": "weekly",
                        "cron": "0 30 9 * * MON,WED,FRI",
                        "timezone": "Asia/Seoul",
                        "time_of_day": "09:30",
                        "weekdays": ["MON", "WED", "FRI"],
                    },
                },
                "active": True,
                "template": False,
            },
            "service_tokens": {},
        }
    )

    assert request.workflow.trigger is not None
    assert request.workflow.trigger.type == "schedule"
    assert request.workflow.trigger.config["schedule_mode"] == "weekly"
