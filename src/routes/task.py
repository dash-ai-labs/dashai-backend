from datetime import datetime
from enum import Enum
import json

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from src.database.email import Email
from src.database.task import EmailTask, TaskStatus
from src.database.db import get_db
from src.libs.const import OPENAI_API_KEY
from src.routes.middleware import get_user_id
from sqlalchemy.orm import Session

import openai

client = openai.OpenAI(api_key=OPENAI_API_KEY)
router = APIRouter()


class TaskActionType(Enum):
    create = "create"
    update = "update"
    delete = "delete"


functions = [
    {
        "name": "create_action_task",
        "description": "Uses an email to create an action based task for the user containing the details from the email and any actionable items",
        "strict": True,
        "parameters": {
            "type": "object",
            "required": ["title", "description", "due_date"],
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the actionable task summarizing the task from the email",
                },
                "description": {
                    "type": "string",
                    "description": "Description of the actionable task with details from the email",
                },
                "due_date": {
                    "type": "string",
                    "description": "Optional due date for the task, formatted as YYYY-MM-DD",
                },
            },
            "additionalProperties": False,
        },
    }
]


def _create_task(
    title: str,
    description: str,
    email_account_id: str,
    email_id: str,
    due_date: str,
    db: Session,
):
    due_date_obj = datetime.strptime(due_date, "%Y-%m-%d")
    task = EmailTask(
        title=title,
        description=description,
        email_account_id=email_account_id,
        email_id=email_id,
        due_date=due_date_obj,
        status=TaskStatus.PENDING,
    )
    db.add(task)
    db.commit()
    return task.to_dict()


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
                                "content": "You are a helpful assistant that creates actionable tasks from emails.",
                            },
                            {
                                "role": "user",
                                "content": f"Subject: {email.subject}\nBody: {email.raw_content}",
                            },
                        ],
                        functions=functions,
                        function_call="auto",
                    )
                    if response.choices[0].finish_reason == "function_call":
                        function_call = response.choices[0].message.function_call
                        args = json.loads(function_call.arguments)

                        return _create_task(
                            email_account_id=email.email_account_id,
                            email_id=email_id,
                            db=db,
                            **args,
                        )
            elif action == TaskActionType.update:
                task: EmailTask = db.query(EmailTask).filter(EmailTask.id == task_id).first()
                if task.email_account.user_id == user_id and task.email_id == email_id:
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
            elif action == TaskActionType.delete:
                task: EmailTask = db.query(EmailTask).filter(EmailTask.id == task_id).first()
                if task.email_account.user_id == user_id and task.email_id == email_id:
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
            query = db.query(EmailTask).filter(EmailTask.email_account.user_id == user_id)
            if email_account_id:
                query = query.filter(EmailTask.email_account_id == email_account_id)
            if status:
                query = query.filter(EmailTask.status == status)
            tasks = query.offset((page - 1) * limit).limit(limit).all()
            return [task.to_dict() for task in tasks]
    else:
        raise HTTPException(status_code=403, detail="Unauthorized")
