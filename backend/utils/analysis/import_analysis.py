import ast
from pathlib import PurePosixPath


def extract_imports(source: str) -> list[tuple[str, int]]:
    """解析 Python 源码，提取所有 import 语句。

    返回 (module_name, level) 列表。
    level=0 表示绝对 import，level>0 表示相对 import 的层数。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    imports: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, 0))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            level = node.level or 0
            if module:
                imports.append((module, level))
    return imports


def resolve_imports_to_project_files(
    imports: list[tuple[str, int]],
    current_file_path: str,
    project_files: dict[str, str],
) -> list[str]:
    """将 import 列表映射到项目中实际存在的文件路径。"""
    current_dir = str(PurePosixPath(current_file_path).parent)
    matched: list[str] = []

    for module, level in imports:
        # 将模块名转为路径片段
        parts = module.replace(".", "/")

        if level > 0:
            # 相对 import：从当前文件目录向上 level-1 层
            base = PurePosixPath(current_dir)
            for _ in range(level - 1):
                base = base.parent
            candidates = [
                str(base / f"{parts}.py"),
                str(base / parts / "__init__.py"),
            ]
        else:
            # 绝对 import：在项目根目录下查找
            candidates = [
                f"{parts}.py",
                f"{parts}/__init__.py",
            ]

        for candidate in candidates:
            normalized = str(PurePosixPath(candidate))
            found = None
            if normalized in project_files:
                found = normalized
            else:
                # Suffix match for projects uploaded with a root folder prefix
                for pf in project_files:
                    if pf.endswith("/" + normalized):
                        found = pf
                        break
            if found:
                if found not in matched:
                    matched.append(found)
                break

    return matched


def get_related_files(
    file_path: str,
    project_files: dict[str, str],
    max_files: int = 5,
    max_lines: int = 200,
) -> list[tuple[str, str]]:
    """获取当前文件通过 import 引用的相关项目文件。

    返回 (path, content) 列表，内容超过 max_lines 行会被截断。
    """
    source = project_files.get(file_path, "")
    if not source:
        return []

    imports = extract_imports(source)
    related_paths = resolve_imports_to_project_files(imports, file_path, project_files)

    results: list[tuple[str, str]] = []
    for path in related_paths[:max_files]:
        content = project_files[path]
        lines = content.split("\n")
        if len(lines) > max_lines:
            content = "\n".join(lines[:max_lines]) + f"\n# ... (已截断，共 {len(lines)} 行)"
        results.append((path, content))

    return results
