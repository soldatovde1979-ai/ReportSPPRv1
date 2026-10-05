# ----------------------------------------------------------------------
# exec_notebook.py — один прогон ноутбука на стенде самопроверки; вызывает run.py, отдельно запускать не нужно
# ЧТО: ячейки кода .ipynb исполняются как есть, по порядку, в одном пространстве имён (как в Colab); /content → рабочая
#      папка прогона; Colab, openai, gspread — заглушки (stubs/), модель — подставная (stubs/fake_model.py).
#      Итог — <рабочая папка>/stand_result.json: дошёл ли прогон до конца, на какой ячейке упал, вызовы модели по этапам,
#      скачанные файлы, строки лога в Sheets.
# Вход: python exec_notebook.py <ноутбук.ipynb> <рабочая папка>; параметры — переменные окружения от run.py:
#      NB_UPLOAD (файлы окна загрузки через «;»), NB_DRIVE (never / always), NB_DEBUG (1 — включить лог в Sheets),
#      NB_AI_FILE (ответы подставной модели), FAIL_MODE (errors — сбои модели).
# ----------------------------------------------------------------------
import sys
sys.dont_write_bytecode = True                      # стенд не оставляет __pycache__ в проекте
import ast, asyncio, json, os, re, time, traceback
from collections import Counter

NB, WORK = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "stubs"))
work = WORK.replace("\\", "/")                      # путь подставляется в строки кода ячеек — только прямые слэши
cells = [c["source"] if isinstance(c["source"], str) else "".join(c["source"])
         for c in json.load(open(NB, encoding="utf-8"))["cells"] if c["cell_type"] == "code"]


def patch(pattern, repl, name):
    """Параметр, который задаёт стенд: строка должна найтись в ноутбуке ровно один раз, иначе стенд не знает, что меняет."""
    hits = [(i, len(re.findall(pattern, s, re.M))) for i, s in enumerate(cells)]
    hits = [(i, n) for i, n in hits if n]
    if len(hits) != 1 or hits[0][1] != 1:
        raise RuntimeError(f"стенд не нашёл в ноутбуке строку {name} ровно один раз — формат строки изменился, "
                           f"поправьте exec_notebook.py")
    cells[hits[0][0]] = re.sub(pattern, repl, cells[hits[0][0]], flags=re.M)


patch(r'^DRIVE_MODE = "\w+"', f'DRIVE_MODE = "{os.environ.get("NB_DRIVE", "never")}"', "DRIVE_MODE")
if os.environ.get("NB_DEBUG") == "1":
    patch(r'^IS_DEBUG = \d+', 'IS_DEBUG = 1', "IS_DEBUG")
cells = [s.replace("/content", work) for s in cells]

result = {"ok": False, "cell": None, "error": ""}
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
g = {"__name__": "__main__"}
t0 = time.time()
try:
    for n, src in enumerate(cells, 1):
        result["cell"] = n
        print(f"\n======== ячейка {n} ========", flush=True)
        r = eval(compile(src, f"<ячейка {n}>", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT), g)
        if asyncio.iscoroutine(r):
            loop.run_until_complete(r)
    result.update(ok=True, cell=None)
except Exception as e:
    result["error"] = f"{type(e).__name__}: {e}"
    traceback.print_exc()
finally:
    import fake_model, gspread
    from google.colab import files
    result["calls"] = dict(Counter(stage for stage, *_ in fake_model.LOG))
    result["downloads"] = [os.path.basename(p) for p in files.downloaded]
    result["sheets"] = {title: ws.rows for title, ws in gspread.BOOK.sheets.items()}
    result["sec"] = round(time.time() - t0, 1)
    with open(os.path.join(WORK, "stand_result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1, default=str)
sys.exit(0 if result["ok"] else 1)
