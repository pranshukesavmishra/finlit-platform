"""Static guard found by the first real run of the job supervisor: `refresh-listing` had crashed with UnboundLocalError for weeks, because main() imports DhanClient locally
in ANOTHER command's branch, which makes the name local to the whole function. Every worker command must bind the names it imports before it uses them."""
import ast
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "finlit/worker.py").read_text()


def _main_fn():
    tree = ast.parse(SRC)
    return next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "main")


def test_every_name_main_imports_locally_is_imported_before_use_in_the_same_command_branch():
    fn = _main_fn()
    local_imports = {a.asname or a.name.split(".")[0] for n in ast.walk(fn) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    top = [s for s in fn.body]
    problems = []

    def check(body, bound):
        """body: statements run in order; bound: names already imported on the way here."""
        bound = set(bound)
        for stmt in body:
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                bound |= {a.asname or a.name.split(".")[0] for a in stmt.names}
                continue
            if isinstance(stmt, ast.If):
                loads = {n.id for n in ast.walk(stmt.test) if isinstance(n, ast.Name)}
                problems.extend((n, stmt.lineno) for n in loads & local_imports - bound)
                both = check(stmt.body, bound) & check(stmt.orelse, bound) if stmt.orelse else check(stmt.body, bound) and bound
                bound |= both
                continue
            if isinstance(stmt, ast.Try):
                for part in (stmt.body, stmt.orelse, stmt.finalbody, *[h.body for h in stmt.handlers]):
                    bound |= check(part, bound) or set()
                continue
            if isinstance(stmt, (ast.With, ast.AsyncWith, ast.For, ast.AsyncFor, ast.While)):
                for item in getattr(stmt, "items", []):
                    for n in ast.walk(item):
                        if isinstance(n, ast.Name) and n.id in local_imports and n.id not in bound:
                            problems.append((n.id, stmt.lineno))
                bound |= check(stmt.body, bound) or set()
                continue
            for n in ast.walk(stmt):
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in local_imports and n.id not in bound:
                    problems.append((n.id, getattr(n, "lineno", stmt.lineno)))
        return bound

    check(top, set())
    assert not problems, f"names used before their local import in main(): {sorted(set(problems))}"
