from utils.logger import log


class TodoService:
    def __init__(self):
        self._todos: dict[str, list[dict]] = {}  # user_id -> list of todos

    def add_todo(self, user_id: str, title: str, priority: int = 0) -> dict:
        if user_id not in self._todos:
            self._todos[user_id] = []

        todo = {
            "title": title,
            "priority": priority,
            "done": False,
        }
        self._todos[user_id].append(todo)
        log(f"Todo added for user {user_id}: {title}")
        return todo

    def get_todos(self, user_id: str, sort_by_priority: bool = True) -> list[dict]:
        todos = self._todos.get(user_id, [])
        if sort_by_priority:
            return sorted(todos, key=lambda t: t["priority"])
        return list(todos)

    def complete_todo(self, user_id: str, index: int) -> bool:
        todos = self._todos.get(user_id, [])
        if 0 <= index < len(todos):
            todos[index]["done"] = True
            log(f"Todo completed for user {user_id}: {todos[index]['title']}")
            return True
        return False

    def delete_todo(self, user_id: str, index: int) -> bool:
        todos = self._todos.get(user_id, [])
        if 0 <= index < len(todos):
            removed = todos.pop(index)
            log(f"Todo deleted for user {user_id}: {removed['title']}")
            return True
        return False

    def get_stats(self, user_id: str) -> dict:
        todos = self._todos.get(user_id, [])
        total = len(todos)
        completed = sum(1 for t in todos if t["done"])
        return {
            "total": total,
            "completed": completed,
            "pending": total - completed,
        }
