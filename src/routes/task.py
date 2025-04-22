import json
from datetime import datetime
from enum import Enum

import openai
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from src.database.db import get_db
from src.database.email import Email
from src.database.email_account import EmailAccount
from src.database.task import EmailTask, TaskStatus
from src.libs.const import OPENAI_API_KEY
from src.routes.middleware import get_user_id

client = openai.OpenAI(api_key=OPENAI_API_KEY)
router = APIRouter()


class TaskActionType(Enum):
    create = "create"
    update = "update"
    archive = "archive"


tools = [
    {
        "type": "function",
        "function": {
            "name": "create_action_task",
            "description": "Uses an email to create an action based task for the user containing the details from the email and any actionable items",
            "strict": True,
            "parameters": {
                "type": "object",
                "required": [
                    "task_actions",
                    "thumbnail_url",
                ],
                "properties": {
                    "task_actions": {
                        "type": "array",
                        "description": "Array of task actions to be taken based on the email. Each action should be an object with a url and url_text.",
                        "items": {
                            "type": "object",
                            "required": ["title", "description", "due_date", "url", "url_text"],
                            "properties": {
                                "url": {
                                    "type": "string",
                                    "description": "Optional URL that is mentioned in the email for the primary action. For example, a link to a product or service, a calendar invite, a tracking link, etc.",
                                },
                                "url_text": {
                                    "type": "string",
                                    "description": "Optional text that is mentioned in the email for the primary action to describe the URL. For example, 'Click here to view', 'Learn more', 'Sign up','Schedule meeting', 'Track order', etc.",
                                },
                                "title": {
                                    "type": "string",
                                    "description": "Title of the actionable task summarizing the task from the email",
                                },
                                "description": {
                                    "type": "string",
                                    "description": "Description of the actionable task with details from the email. Should be less than 150 characters.",
                                },
                                "due_date": {
                                    "type": "string",
                                    "description": "Optional due date for the task, formatted as YYYY-MM-DD",
                                },
                            },
                            "additionalProperties": False,
                        },
                    },
                    "thumbnail_url": {
                        "type": ["string", "null"],
                        "description": "Optional thumbnail URL of sender of the email. This should be from the email content only.",
                    },
                },
                "additionalProperties": False,
            },
        },
    }
]


def _create_task(
    db: Session,
    title: str,
    description: str,
    email_account_id: str,
    email_id: str,
    due_date: str,
    url: str = None,
    url_text: str = None,
    thumbnail_url: str = None,
):

    due_date_obj = datetime.strptime(due_date, "%Y-%m-%d")
    task = EmailTask(
        title=title,
        description=description,
        email_account_id=email_account_id,
        email_id=email_id,
        due_date=due_date_obj,
        status=TaskStatus.PENDING,
        url=url,
        url_text=url_text,
        thumbnail_url=thumbnail_url,
    )

    return task


@router.post("/user/{user_id}/task")
async def email_task_action(
    request: Request,
    user_id: str,
    email_id: str = Body(...),
    action: TaskActionType = Body(...),
    task_id: str = Body(None),
    status: TaskStatus = Body(None),
    due_date: str = Body(None),
    title: str = Body(None),
    description: str = Body(None),
    user=Depends(get_user_id),
):
    if user_id == user.get("user_id"):
        with get_db() as db:
            if action == TaskActionType.create:
                email = db.query(Email).filter(Email.id == email_id).first()
                if email:
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {
                                "role": "system",
                                "content": "You are a helpful assistant that creates actionable tasks from emails. Today's date is "
                                + datetime.now().strftime("%Y-%m-%d"),
                            },
                            {
                                "role": "user",
                                "content": f"Subject: {email.subject}\nBody: {email.raw_content}",
                            },
                        ],
                        tools=tools,
                    )
                    function_call = response.choices[0].message.tool_calls[0]
                    arguments = json.loads(function_call.function.arguments)
                    task_actions = arguments["task_actions"]
                    thumbnail_url = arguments["thumbnail_url"]
                    tasks = [
                        _create_task(
                            email_account_id=email.email_account_id,
                            email_id=email_id,
                            db=db,
                            thumbnail_url=thumbnail_url,
                            **args,
                        )
                        for args in task_actions
                    ]
                    db.add_all(tasks)
                    db.commit()
                    return [task.to_dict() for task in tasks]
            elif action == TaskActionType.update:
                task: EmailTask = db.query(EmailTask).filter(EmailTask.id == task_id).first()
                if str(task.email_account.user_id) == user_id and str(task.email_id) == email_id:
                    update_dict = {}
                    if status:
                        update_dict["status"] = status
                    if due_date:
                        update_dict["due_date"] = datetime.strptime(due_date, "%Y-%m-%d")
                    if title:
                        update_dict["title"] = title
                    if description:
                        update_dict["description"] = description
                    for key, value in update_dict.items():
                        setattr(task, key, value)
                    db.commit()
                    return task.to_dict()
                else:
                    raise HTTPException(status_code=403, detail="Unauthorized")
            elif action == TaskActionType.archive:
                task: EmailTask = db.query(EmailTask).filter(EmailTask.id == task_id).first()

                if str(task.email_account.user_id) == user_id and str(task.email_id) == email_id:
                    task.status = TaskStatus.ARCHIVED
                    db.commit()
                    return task.to_dict()
                else:
                    raise HTTPException(status_code=403, detail="Unauthorized")


@router.get("/user/{user_id}/tasks")
async def get_tasks(
    request: Request,
    user_id: str,
    email_account_id: str = Query(None),
    status: TaskStatus = Query(None),
    page: int = Query(1),
    limit: int = Query(10),
    user=Depends(get_user_id),
):
    if user_id == user.get("user_id"):
        with get_db() as db:
            # Get all email accounts for the user
            user_email_accounts = (
                db.query(EmailAccount).filter(EmailAccount.user_id == user_id).all()
            )
            email_account_ids = [account.id for account in user_email_accounts]

            # Query tasks for all email accounts belonging to the user
            query = db.query(EmailTask).filter(EmailTask.email_account_id.in_(email_account_ids))
            if email_account_id:
                query = query.filter(EmailTask.email_account_id == email_account_id)
            if status:
                query = query.filter(EmailTask.status == status)
            tasks = query.offset((page - 1) * limit).limit(limit).all()
            return [task.to_dict() for task in tasks]
    else:
        raise HTTPException(status_code=403, detail="Unauthorized")
