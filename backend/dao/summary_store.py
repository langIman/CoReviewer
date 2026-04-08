from backend.dao.database import get_connection


def save_summary(path: str, type_: str, summary: str, project_name: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO summaries (path, type, summary, project_name) VALUES (?, ?, ?, ?)",
        (path, type_, summary, project_name),
    )
    conn.commit()
    conn.close()


def clear_project_summaries(project_name: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM summaries WHERE project_name = ?", (project_name,))
    conn.commit()
    conn.close()


def get_summaries_by_type(project_name: str, type_: str) -> list[dict]:
    """查询指定项目的某类摘要（file/folder/project）。"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT path, summary FROM summaries WHERE project_name = ? AND type = ?",
        (project_name, type_),
    ).fetchall()
    conn.close()
    return [{"path": row[0], "summary": row[1]} for row in rows]
