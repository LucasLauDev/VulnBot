import json
import re
from typing import List, Dict

from pydantic import BaseModel

from config.config import Configs
from prompts.prompt import DeepPentestPrompt
from db.models.plan_model import Plan
from db.models.task_model import TaskModel, Task
from server.chat.chat import _chat


class WritePlan(BaseModel):
    plan_chat_id: str

    def run(self, init_description) -> str:
        rsp, _ = _chat(query=DeepPentestPrompt.write_plan, conversation_id=self.plan_chat_id, kb_name=Configs.kb_config.kb_name, kb_query=init_description)
        extracted = self._extract_plan_json(rsp)
        if extracted is None:
            preview = (rsp or "")[:800]
            raise ValueError(
                "Plan model response had no parseable <json>...</json> task list. "
                f"Preview: {preview!r}"
            )
        return extracted

    @staticmethod
    def _extract_plan_json(rsp: str | None) -> str | None:
        if rsp is None:
            return None
        match = re.search(r"<json>(.*?)</json>", rsp, re.DOTALL)
        if match:
            return match.group(1).strip()
        fence = re.search(r"```(?:json)?\s*(\[[\s\S]*?])\s*```", rsp, re.IGNORECASE)
        if fence:
            return fence.group(1).strip()
        stripped = rsp.strip()
        if stripped.startswith("["):
            end = stripped.rfind("]")
            if end != -1:
                return stripped[: end + 1]
        return None

    def update(self, task_result, success_task, fail_task, init_description) -> str:
        rsp, _ = _chat(
            query=DeepPentestPrompt.update_plan.format(current_task=task_result.instruction,
                                                      init_description=init_description,
                                                      current_code=task_result.code,
                                                      task_result=task_result.result,
                                                      success_task=success_task,
                                                      fail_task=fail_task),
            conversation_id=self.plan_chat_id,
            kb_name=Configs.kb_config.kb_name,
            kb_query=task_result.instruction
        )
        if rsp == "":
            return rsp

        return self._extract_plan_json(rsp)


def parse_tasks(response: str, current_plan: Plan):
    if response is None or (isinstance(response, str) and not str(response).strip()):
        raise ValueError("Plan JSON string is empty or missing")
    response = json.loads(response)

    tasks = import_tasks_from_json(current_plan.id, response)

    current_plan.tasks = tasks

    return current_plan

def preprocess_json_string(json_str):
     # Use a regular expression to find invalid escape sequences
    json_str = re.sub(r'\\([@!])', r'\\\\\1', json_str)

    return json_str

def merge_tasks(response: str, current_plan: Plan):

    if response is None or not str(response).strip():
        raise ValueError("merge_tasks: empty plan update JSON")

    # Preprocess the input JSON string
    processed_response = preprocess_json_string(response)

    response = json.loads(processed_response)

    tasks = merge_tasks_from_json(current_plan.id, response, current_plan.tasks)

    current_plan.tasks = tasks

    return current_plan


def import_tasks_from_json(plan_id: str, tasks_json: List[Dict]) -> List[TaskModel]:
    tasks = []
    for idx, task_data in enumerate(tasks_json):
        task = Task(
            plan_id=plan_id,
            sequence=idx,
            action=task_data['action'],
            instruction=task_data['instruction'],
            dependencies=[i for i, t in enumerate(tasks_json)
                          if t['id'] in task_data['dependent_task_ids']]
        )

        tasks.append(task)
    return tasks


def merge_tasks_from_json(plan_id: str, new_tasks_json: List[Dict], old_tasks: List[Task]) -> List[Task]:
    # 获取所有已完成且成功的任务
    completed_tasks_map = {
        task.instruction: task
        for task in old_tasks
        if task.is_finished and task.is_success
    }

    merged_tasks = []

    for instruction, completed_task in completed_tasks_map.items():
        found = False
        for task_data in new_tasks_json:
            if task_data['instruction'] == instruction:
                found = True
                break
        if not found:
            completed_task.sequence = len(merged_tasks)
            completed_task.dependencies = []
            merged_tasks.append(completed_task)

    new_task_id_to_idx = {
        task_data.get('id'): idx+len(merged_tasks)
        for idx, task_data in enumerate(new_tasks_json)
    }
    for idx, task_data in enumerate(new_tasks_json):
        instruction = task_data['instruction']
        sequence = len(merged_tasks)

        if instruction in completed_tasks_map:
            existing_task = completed_tasks_map[instruction]
            existing_task.sequence = sequence
            existing_task.dependencies = [
                new_task_id_to_idx[dep_id]
                for dep_id in task_data['dependent_task_ids']
                if dep_id in new_task_id_to_idx
            ]
            merged_tasks.append(existing_task)
        else:
            new_task = Task(
                plan_id=plan_id,
                sequence=sequence,
                action=task_data['action'],
                instruction=task_data['instruction'],
                dependencies=[
                    new_task_id_to_idx[dep_id]
                    for dep_id in task_data['dependent_task_ids']
                    if dep_id in new_task_id_to_idx
                ],
            )
            merged_tasks.append(new_task)

    return merged_tasks