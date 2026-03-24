from models.user import User
from services.auth_service import AuthService
from services.todo_service import TodoService


def main():
    auth = AuthService()
    todo_service = TodoService()

    # 注册用户
    alice = auth.register("alice", "alice@example.com", "password123")
    bob = auth.register("bob", "bob@example.com", "qwerty")

    # 登录
    token = auth.login("alice", "password123")
    if not token:
        print("Login failed!")
        return

    current_user = auth.get_user_by_token(token)
    print(f"Welcome, {current_user.username}!")

    # 添加待办事项
    todo_service.add_todo(current_user.id, "Buy groceries", priority=2)
    todo_service.add_todo(current_user.id, "Write unit tests", priority=1)
    todo_service.add_todo(current_user.id, "Deploy to production", priority=3)

    # 查看待办
    todos = todo_service.get_todos(current_user.id)
    print(f"\n{current_user.username}'s TODOs:")
    for todo in todos:
        status = "done" if todo["done"] else "pending"
        print(f"  [{status}] {todo['title']} (priority: {todo['priority']})")

    # 完成一个任务
    todo_service.complete_todo(current_user.id, 0)

    # 获取统计
    stats = todo_service.get_stats(current_user.id)
    print(f"\nStats: {stats['completed']}/{stats['total']} completed")


if __name__ == "__main__":
    main()
