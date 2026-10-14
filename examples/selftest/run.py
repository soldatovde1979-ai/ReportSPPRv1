# ----------------------------------------------------------------------
# run.py — стенд самопроверки ReportSPPR: ноутбук целиком на подставной модели — без ключей, сети и токенов
# ЧТО: прогоняет ноутбук (ячейки как есть, exec_notebook.py) в семи сценариях и сверяет отчёт:
#      а) демо-выгрузка → отчёт = макет examples/mockup_report_v2.html, кроме известных отличий; лог CSV пишется;
#      б) боевая выгрузка → отчёт ноутбука = прямая сборка модулем, кроме журнала ИИ;
#      в) сбои модели (обрыв JSON, негодная строка, чужой номер, неизвестный ключ, не-JSON) → отчёт собирается, повторы есть;
#      г) Диск: модуль и шаблон найдены в папке проекта (src/), история записана; повтор → 0 вызовов, тот же отчёт;
#      д) шаблон чужого мажора, нет модуля → остановка в ячейке 1, до вызовов модели;
#      е) модуль и шаблон «с GitHub» (file:// этой папки) → отчёт = прямая сборка; GitHub недоступен → запасная копия
#         с Диска с предупреждением, без копии — остановка в ячейке 1;
#      ж) локальный запуск (без Colab): ИИ — opencoder, файлы — папка проекта, лог — CSV → отчёт = прямая сборка;
#         прокси не запущен → остановка в ячейке 1; DeepSeek с ключом из .env → прогон проходит.
# ПОЧЕМУ: my-FT Т-72 — «единый тест сэкономит деньги и время»: правка проверяется за секунды, а не боевым прогоном
#         (02.10 — 608 тыс. токенов). Качество ответов настоящей модели стенд не проверяет — только боевой прогон.
# Запуск из любой папки:  Linux / Bash — python3 examples/selftest/run.py
#                         Windows / PowerShell — py examples\selftest\run.py
# Нужно: Python 3.10+ и jinja2. В проект ничего не пишет: работа — во временной папке, при успехе она удаляется.
# Итог: «ИТОГ: ОК» и код возврата 0; иначе — что разошлось, код 1 и путь к рабочей папке (вывод ноутбука — stdout.txt).
# ----------------------------------------------------------------------
VERSION = "2.2"                                   # 2.2 — «ж»: параметр из .env, рабочая копия run/, строки прогресса; 2.1 — лог CSV вместо Sheets (сценарий «а»); 2.0 — папка без номера, ноутбук RepSSPR.ipynb, модуль и шаблон — по мажору ноутбука; сценарий «ж» — локальный запуск; 1.3 — неделя макета MOCK_WEEK задаётся в ноутбуке (REPORT_WEEK); 1.2 — ссылка «Открыть в Colab»
# ----------------------------------------------------------------------
# ЧТО ИЗМЕНЕНО (2.0): имя ноутбука постоянное; модуль и шаблон — по мажору NOTEBOOK_VERSION (вычисляет preflight)
# ПОЧЕМУ: my-FT Р-12 — смена версии не требует правки стенда
# ----------------------------------------------------------------------
NOTEBOOK_FILE = "RepSSPR.ipynb"                   # проверяемый ноутбук: имя постоянное, версия — внутри
MAJOR = MODULE_FILE = TEMPLATE_FILE = None        # src/report_v<МАЖОР>.py и template_v<МАЖОР>.html — задаёт preflight()
MOCKUP_FILE = "examples/mockup_report_v2.html"    # эталон отчёта: макет собирает тот же модуль (build_mockup_v2.py)
AI_FILE = "examples/mockup_v2_ai.json"            # ответы подставной модели — разметка макета
# ЧТО ИЗМЕНЕНО: неделя макета задана явно и подставляется в ноутбук (NB_WEEK) и прямую сборку
# ПОЧЕМУ: модуль 5.6 сменил неделю по умолчанию (прошл. завершённая, W38), а макет и разметка mockup_v2_ai.json
#         собраны под W39 — без фиксации отчёт ноутбука «уезжает» от макета, а разметка не находит свои строки
MOCK_WEEK = 39                                    # ISO-неделя макета = REPORT_WEEK в build_mockup_v2.py
DEMO_DUMP = "examples/sppr_dump_20260929_180748_842rec_demo_tab.json"
REAL_DUMP = "data/sppr_dump_20260929_180748_842rec.json"

# Чем отчёт ноутбука законно отличается от макета: макет собирается с заголовком «Макет…» и плашкой, без журнала ИИ.
# Название → (операция, кусок «было», кусок «стало»); пустая строка — не проверяется.
KNOWN_DIFFS = {
    "заголовок вкладки": ("replace", "Макет v2 — Качество 1С-поддержки", "Качество 1С-поддержки"),
    "плашка «Макет»": ("delete", '<div class="mock">', ""),
    "сноска паспорта о расходе ИИ": ("replace", "Расход токенов в макете не считается", "Расход ИИ этого прогона"),
    "таблица «Расход ИИ по этапам»": ("insert", "", "<h3>Расход ИИ по этапам</h3>"),
}
RUN_LOG_DIFFS = ["сноска паспорта о расходе ИИ", "таблица «Расход ИИ по этапам»"]

import sys
sys.dont_write_bytecode = True                    # стенд не оставляет __pycache__ в проекте
import difflib, glob, importlib.util, json, os, pathlib, re, shutil, socket, subprocess, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(os.path.dirname(os.path.dirname(HERE)))  # корень репозитория
sys.stdout.reconfigure(errors="replace")
TMP = ""
STATE = {}                                        # итоги сценариев, нужные следующим (вызовы модели в «б» — база для «в»)


class Fail(Exception):
    """Расхождение сценария; текст — что не так."""


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def short(s, n=160):
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[:n] + "…"


def load_module():
    spec = importlib.util.spec_from_file_location(f"report_v{MAJOR}", MODULE_FILE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def hunks(a, b):
    """Отличия двух HTML по тегам и кускам текста: [(операция, было, стало)]."""
    tok = lambda s: re.findall(r"<[^>]+>|[^<]+", s)
    ta, tb = tok(a), tok(b)
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    return [(op, "".join(ta[i1:i2]), "".join(tb[j1:j2])) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"]


def expect_diffs(a, b, names, what):
    """Отличия b от a — ровно известные отличия names, каждое один раз; иначе Fail с перечнем лишних и недостающих."""
    left, extra = list(names), []
    for op, x, y in hunks(a, b):
        hit = next((n for n in left if KNOWN_DIFFS[n][0] == op and KNOWN_DIFFS[n][1] in x and KNOWN_DIFFS[n][2] in y), None)
        if hit:
            left.remove(hit)
        else:
            extra.append(f"{op}: было «{short(x)}» → стало «{short(y)}»")
    if extra or left:
        msg = [f"{what}: лишних отличий {len(extra)}"] if extra else []
        msg += [f"{what}: нет ожидаемых отличий — {', '.join(left)}"] if left else []
        raise Fail("; ".join(msg) + "".join(f"\n        {e}" for e in extra[:5]))


def calls(r, word):
    return sum(n for stage, n in r["calls"].items() if word in stage)


def notebook_param(name):
    """Строковый параметр ячейки 1 ноутбука, например DRIVE_ROOT."""
    src = "\n".join(c["source"] if isinstance(c["source"], str) else "".join(c["source"])
                    for c in json.load(open(NOTEBOOK_FILE, encoding="utf-8"))["cells"] if c["cell_type"] == "code")
    m = re.search(rf"^{name} = ['\"]([^'\"]+)['\"]", src, re.M)
    if not m:
        raise Fail(f"в ноутбуке нет параметра {name}")
    return m.group(1)


def run_nb(tag, dump, upload, drive="never", fail="", debug=False, seed=None, drive_from=None, code="drive", github="",
           extra=None):
    """Один прогон ноутбука в папке TMP/tag. upload — файлы окна загрузки кроме выгрузки; seed(work) — подготовить Диск;
    drive_from — взять Диск из рабочей папки прошлого прогона (повтор недели); code, github — CODE_SOURCE и GITHUB_RAW;
    extra — доп. переменные окружения прогона (NB_ENV, NB_OC_URL, NB_PROVIDER)."""
    work = os.path.join(TMP, tag)
    os.makedirs(work)
    if drive_from:
        shutil.copytree(os.path.join(drive_from, "drive"), os.path.join(work, "drive"))
    if seed:
        seed(work)
    env = dict(os.environ, NB_UPLOAD=";".join(os.path.abspath(p) for p in [dump] + upload), NB_DRIVE=drive,
               NB_DEBUG="1" if debug else "0", NB_AI_FILE=os.path.abspath(AI_FILE), FAIL_MODE=fail,
               NB_CODE=code, NB_GITHUB=github, NB_WEEK=str(MOCK_WEEK),
               PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1", **(extra or {}))
    for k in ("DEEPSEEK_API_KEY", "GEMINI_API_KEY", "GITHUB_TOKEN", "REPORTSPPR_ROOT",
              "AI_PROVIDER", "REPORT_WEEK", "REUSE_AI", "TEST_SAMPLE_SIZE", "IS_DEBUG", "OC_BASE_URL"):
        env.pop(k, None)                          # ключи машины стенда не должны подменять .env и секреты прогона
    p = subprocess.run([sys.executable, os.path.join(HERE, "exec_notebook.py"), os.path.abspath(NOTEBOOK_FILE), work],
                       env=env, capture_output=True, timeout=900)
    out = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
    with open(os.path.join(work, "stdout.txt"), "w", encoding="utf-8") as f:
        f.write(out)
    res_file = os.path.join(work, "stand_result.json")
    r = json.load(open(res_file, encoding="utf-8")) if os.path.exists(res_file) else \
        {"ok": False, "cell": None, "error": "прогон оборвался до итога", "calls": {}, "downloads": []}
    reports = glob.glob(os.path.join(work, "result", "*.html"))
    r.update(out=out, work=work, html=read(reports[0]) if len(reports) == 1 else None)
    return r


def need_ok(r, what):
    if not r["ok"]:
        tail = "\n        ".join(r["out"].strip().splitlines()[-6:])
        raise Fail(f"{what}: ноутбук остановился в ячейке {r['cell']}: {r['error']}\n        {tail}")
    if r["html"] is None:
        raise Fail(f"{what}: отчёт не найден в {r['work']}/result")


def tools():
    """Модуль и шаблон, «выбранные в окне загрузки» вместе с выгрузкой."""
    return [TEMPLATE_FILE, MODULE_FILE]


def scen_a():
    r = run_nb("a", DEMO_DUMP, tools(), debug=True)
    need_ok(r, "прогон")
    try:
        expect_diffs(read(MOCKUP_FILE), r["html"], list(KNOWN_DIFFS), "отчёт против макета")
    except Fail as e:
        raise Fail(f"{e}\n        изменение задумано — пересоберите макет (python3 examples/build_mockup_v2.py), "
                   f"проверьте его diff и закоммитьте вместе с правкой; не задумано — ищите ошибку")
    # ЧТО ИЗМЕНЕНО (2.1): лог IS_DEBUG — CSV и в Colab (Sheets убран, my-FT В-27); без Диска — /content/result/logs + скачивание
    rows = [[ln.split(";") for ln in read(p).lstrip("\ufeff").strip().splitlines()] if os.path.exists(p) else []
            for p in (os.path.join(r["work"], "result", "logs", f) for f in ("Logs.csv", "Token.csv"))]
    if [len(x) for x in rows] != [2, 2] or len(rows[1][1]) != len(rows[1][0]):
        raise Fail(f"лог CSV (IS_DEBUG = 1): строк в Logs.csv и Token.csv {[len(x) for x in rows]} — ждали заголовок и одну строку")
    if not {"Logs.csv", "Token.csv"} <= set(r["downloads"]):
        raise Fail(f"Colab без Диска: лог не отдан на скачивание, скачано {r['downloads']}")
    return f"отчёт = макет, кроме {len(KNOWN_DIFFS)} известных отличий; лог CSV записан и скачан"


def direct_html():
    """Отчёт по боевой выгрузке, собранный модулем напрямую, — эталон для «б» и «е»."""
    rv = load_module()
    R = rv.load(json.load(open(REAL_DUMP, encoding="utf-8-sig")), os.path.basename(REAL_DUMP), MOCK_WEEK, [],
                 demo=False, say=lambda *a, **k: None)
    rv.attach_ai(R, json.load(open(AI_FILE, encoding="utf-8")))
    return rv.render(R, read(TEMPLATE_FILE))


def scen_b():
    r = run_nb("b", REAL_DUMP, tools())
    need_ok(r, "прогон")
    expect_diffs(direct_html(), r["html"], RUN_LOG_DIFFS, "отчёт ноутбука против прямой сборки модулем")
    STATE["b"] = r
    return "отчёт ноутбука = прямая сборка модулем, кроме журнала ИИ"


def scen_v():
    base = STATE.get("b")
    if not base:
        raise Fail("нет базы для сравнения вызовов — сценарий «б» не прошёл")
    r = run_nb("v", REAL_DUMP, tools(), fail="errors")
    need_ok(r, "прогон со сбоями модели")
    probs = []
    m = re.search(r"размечено (\d+) из (\d+)", r["out"])
    if not m or m.group(1) != m.group(2):
        probs.append("после обрыва JSON и негодной строки размечены не все решённые")
    if calls(r, "РАЗМЕТКА РЕШЁННЫХ") <= calls(base, "РАЗМЕТКА РЕШЁННЫХ"):
        probs.append("обрыв JSON и негодная строка не дали повторных вызовов разметки")
    if calls(r, "КРИТИЧНЫЕ ОТКРЫТЫЕ") != calls(base, "КРИТИЧНЫЕ ОТКРЫТЫЕ") + 1:
        probs.append("номер не из выгрузки в критичных открытых не вызвал повтор")
    # разборы: s3 — один повтор из-за неизвестного ключа, s8 — ещё две попытки (всего три) на ответ не-JSON
    if calls(r, "РАЗБОР СЛАЙДА") != calls(base, "РАЗБОР СЛАЙДА") + 3:
        probs.append(f"разборов слайдов {calls(r, 'РАЗБОР СЛАЙДА')}, ждали {calls(base, 'РАЗБОР СЛАЙДА') + 3}: "
                     f"повтор по неизвестному ключу или три попытки на не-JSON не сработали")
    if r["html"].count("Разбор ИИ недоступен: сбой модели") != 1:
        probs.append("у слайда без разбора нет нейтральной строки «Разбор ИИ недоступен»")
    if probs:
        raise Fail("; ".join(probs))
    return "обрыв JSON, негодная строка, чужой номер, неизвестный ключ, не-JSON — отчёт собран, повторы сработали"


def on_disk(work, p):
    """Путь Colab /content/... внутри рабочей папки прогона."""
    return p.replace("/content", work.replace("\\", "/"))


def seed_drive(work):
    """Папка проекта на Диске — как репозиторий: шаблон в корне, модуль в src/."""
    root = on_disk(work, notebook_param("DRIVE_ROOT"))
    os.makedirs(os.path.join(root, "src"))
    shutil.copy(TEMPLATE_FILE, root)
    shutil.copy(MODULE_FILE, os.path.join(root, "src"))


def scen_g():
    history_dir = notebook_param("HISTORY_DIR")
    r1 = run_nb("g1", DEMO_DUMP, [], drive="always", seed=seed_drive)
    need_ok(r1, "первый прогон с Диском")
    weeks = glob.glob(os.path.join(on_disk(r1["work"], history_dir), "week_*.json"))
    if not weeks:
        raise Fail("история недель не записана на Диск")
    r2 = run_nb("g2", DEMO_DUMP, [], drive="always", drive_from=r1["work"])
    need_ok(r2, "повтор недели")
    probs = []
    if sum(r2["calls"].values()):
        probs.append(f"повтор из кэша вызвал модель {sum(r2['calls'].values())} раз")
    if "изменилось 0" not in r2["out"]:
        probs.append("повтор той же выгрузки изменил историю недель")
    table = re.compile(r'<section class="panel "><header class="ph"><h3>Расход ИИ по этапам</h3>.*?</section>', re.S)
    h = hunks(table.sub("", r1["html"]), table.sub("", r2["html"]))
    if h:
        probs.append(f"отчёт повтора отличается от первого ({len(h)}): " + "; ".join(f"{op}: «{short(x)}» → «{short(y)}»" for op, x, y in h[:3]))
    if probs:
        raise Fail("; ".join(probs))
    return f"модуль найден в src/ на Диске, история записана ({len(weeks)} нед.); повтор — 0 вызовов, тот же отчёт"


def scen_d():
    probs = []
    bad_dir = os.path.join(TMP, "d_template")
    os.makedirs(bad_dir)
    text, n = re.subn(r'TEMPLATE_VERSION = "\d+\.\d+"', f'TEMPLATE_VERSION = "{MAJOR - 1}.9"', read(TEMPLATE_FILE), count=1)
    if not n:
        raise Fail(f"в {TEMPLATE_FILE} нет строки TEMPLATE_VERSION")
    with open(os.path.join(bad_dir, os.path.basename(TEMPLATE_FILE)), "w", encoding="utf-8") as f:
        f.write(text)
    checks = [("шаблон чужого мажора", run_nb("d1", REAL_DUMP, [os.path.join(bad_dir, os.path.basename(TEMPLATE_FILE)), MODULE_FILE]), "мажор"),
              ("нет модуля", run_nb("d2", REAL_DUMP, [TEMPLATE_FILE]), f"Не найден {os.path.basename(MODULE_FILE)}")]
    for what, r, word in checks:
        if r["ok"] or r["cell"] != 1 or word not in r["error"]:
            probs.append(f"{what}: ждали остановку в ячейке 1 с «{word}», вышло: "
                         + ("прогон прошёл" if r["ok"] else f"ячейка {r['cell']}, {short(r['error'])}"))
        if sum(r["calls"].values()):
            probs.append(f"{what}: модель вызвана {sum(r['calls'].values())} раз до остановки")
    if probs:
        raise Fail("; ".join(probs))
    return "оба случая остановлены в ячейке 1, модель не вызывалась"


def scen_e():
    repo = pathlib.Path(".").resolve().as_uri()   # «GitHub» = эта папка репозитория: сеть не нужна
    gone = repo + "/missing"                      # «GitHub недоступен»
    probs = []
    r = run_nb("e1", REAL_DUMP, [], code="github", github=repo)
    need_ok(r, "модуль и шаблон с GitHub")
    if "(GitHub)" not in r["out"]:
        probs.append("в строке «🧩» нет пометки (GitHub)")
    expect_diffs(direct_html(), r["html"], RUN_LOG_DIFFS, "отчёт с модулем с GitHub против прямой сборки")
    r = run_nb("e2", REAL_DUMP, [], drive="always", seed=seed_drive, code="github", github=gone)
    need_ok(r, "GitHub недоступен, запасная копия на Диске")
    if "взята запасная копия" not in r["out"] or "(запасная копия)" not in r["out"]:
        probs.append("GitHub недоступен: нет предупреждения о запасной копии")
    r = run_nb("e3", REAL_DUMP, [], code="github", github=gone)
    if r["ok"] or r["cell"] != 1 or "GitHub недоступен" not in r["error"]:
        probs.append("GitHub недоступен и копии нет: ждали остановку в ячейке 1, вышло: "
                     + ("прогон прошёл" if r["ok"] else f"ячейка {r['cell']}, {short(r['error'])}"))
    if sum(r["calls"].values()):
        probs.append(f"GitHub недоступен и копии нет: модель вызвана {sum(r['calls'].values())} раз до остановки")
    if probs:
        raise Fail("; ".join(probs))
    return "с GitHub — отчёт = прямая сборка; GitHub недоступен — запасная копия с Диска с предупреждением, без неё — остановка"


def seed_local(work, dump, env_line=""):
    """Папка проекта на ПК — как репозиторий: модуль в src/, шаблон в корне, выгрузка в source/, ключ — в .env."""
    os.makedirs(os.path.join(work, "src"))
    os.makedirs(os.path.join(work, "source"))
    shutil.copy(TEMPLATE_FILE, work)
    shutil.copy(MODULE_FILE, os.path.join(work, "src"))
    shutil.copy(dump, os.path.join(work, "source"))
    if env_line:
        with open(os.path.join(work, ".env"), "w", encoding="utf-8") as f:
            f.write(env_line + "\n")


def scen_zh():
    probs = []
    proxy = socket.socket()                       # «прокси OpenCoder»: порт слушается — проверка ячейки 1 проходит
    proxy.bind(("127.0.0.1", 0))
    proxy.listen(8)
    up = f"http://127.0.0.1:{proxy.getsockname()[1]}/v1"
    dead = socket.socket()                        # «прокси не запущен»: порт был занят и освобождён
    dead.bind(("127.0.0.1", 0))
    down = f"http://127.0.0.1:{dead.getsockname()[1]}/v1"
    dead.close()
    try:
        local = {"NB_ENV": "local", "NB_OC_URL": up}
        # как run_local.bat: рабочая копия в run/, параметр IS_DEBUG — из .env (строка с комментарием), не из кода
        r = run_nb("zh1", REAL_DUMP, [], drive="never", seed=lambda w: seed_local(w, REAL_DUMP, "IS_DEBUG=1   # лог в CSV"),
                   extra=dict(local, NB_ROOT="1"))
        need_ok(r, "локальный запуск")
        if "⚙️ Параметр из .env: IS_DEBUG = 1" not in r["out"]:
            probs.append("параметр IS_DEBUG из .env не подхвачен (нет строки «⚙️ Параметр из .env»)")
        if not re.search(r"▶️ \[\d\d:\d\d\] Разметка решённых — начат", r["out"]) or not re.search(r"ответов \d+ из \d+", r["out"]):
            probs.append("нет строк прогресса: начало этапа «▶️ [мм:сс]» и счётчик разметки «ответов N из M»")
        if "Провайдер: OPENCODER" not in r["out"] or "(папка проекта)" not in r["out"]:
            probs.append("локально ждали провайдер OPENCODER и модуль из папки проекта")
        if r["downloads"]:
            probs.append(f"локально ноутбук вызвал скачивание браузером: {r['downloads']}")
        expect_diffs(direct_html(), r["html"], RUN_LOG_DIFFS, "локальный отчёт против прямой сборки")
        logs = [os.path.join(r["work"], "result", "logs", f) for f in ("Logs.csv", "Token.csv")]
        rows = [len(read(p).strip().splitlines()) if os.path.exists(p) else 0 for p in logs]
        if rows != [2, 2]:
            probs.append(f"лог CSV (IS_DEBUG = 1): строк в Logs.csv и Token.csv {rows} — ждали заголовок и одну строку")
        if not glob.glob(os.path.join(r["work"], "result", "history", "week_*.json")):
            probs.append("история недель не записана в result/history папки проекта")
        r = run_nb("zh2", REAL_DUMP, [], seed=lambda w: seed_local(w, REAL_DUMP), extra=dict(local, NB_OC_URL=down))
        if r["ok"] or r["cell"] != 1 or "Прокси OpenCoder не отвечает" not in r["error"]:
            probs.append("прокси не запущен: ждали остановку в ячейке 1, вышло: "
                         + ("прогон прошёл" if r["ok"] else f"ячейка {r['cell']}, {short(r['error'])}"))
        if sum(r["calls"].values()):
            probs.append(f"прокси не запущен: модель вызвана {sum(r['calls'].values())} раз до остановки")
        r = run_nb("zh3", REAL_DUMP, [], seed=lambda w: seed_local(w, REAL_DUMP, "DEEPSEEK_API_KEY=stand-key"),
                   extra=dict(local, NB_PROVIDER="deepseek"))
        need_ok(r, "локально DeepSeek с ключом из .env")
        if "Провайдер: DEEPSEEK" not in r["out"]:
            probs.append("локально с AI_PROVIDER = deepseek провайдер не DEEPSEEK")
    finally:
        proxy.close()
    if probs:
        raise Fail("; ".join(probs))
    return "локально: opencoder, файлы из папки проекта, лог в CSV, отчёт = прямая сборка; без прокси — остановка; ключ из .env"


def preflight():
    """Контроль версий до прогонов: ноутбук RepSSPR.ipynb, по его мажору — модуль и шаблон того же мажора, ссылка README."""
    global MAJOR, MODULE_FILE, TEMPLATE_FILE
    if not os.path.exists(NOTEBOOK_FILE):
        raise Fail(f"нет {NOTEBOOK_FILE}")
    old = sorted(glob.glob("RepSSPR_v*.ipynb"))
    if old:
        raise Fail(f"в корне лежат ноутбуки со старым именем {', '.join(old)}: ноутбук один — {NOTEBOOK_FILE}, версия внутри")
    nb_ver = notebook_param("NOTEBOOK_VERSION")
    MAJOR = int(nb_ver.split(".")[0])
    MODULE_FILE, TEMPLATE_FILE = f"src/report_v{MAJOR}.py", f"template_v{MAJOR}.html"
    for path in (MODULE_FILE, TEMPLATE_FILE):
        if not os.path.exists(path):
            raise Fail(f"ноутбук {nb_ver} ищет {path} — файла нет (сменили мажор — переименуйте модуль и шаблон: git mv)")
    majors = sorted(int(m.group(1)) for p in glob.glob("src/report_v*.py") for m in [re.search(r"report_v(\d+)\.py$", p)] if m)
    if majors[-1] != MAJOR:
        raise Fail(f"в src/ есть report_v{majors[-1]}.py, а ноутбук {nb_ver} — мажор {MAJOR}: поднимите NOTEBOOK_VERSION")
    rv = load_module()
    tpl_ver = rv.check_template(read(TEMPLATE_FILE))
    bad = [f"{k} {v}" for k, v in {"модуль": rv.VERSION, "шаблон": tpl_ver}.items() if int(v.split(".")[0]) != MAJOR]
    if bad:
        raise Fail(f"ноутбук {nb_ver}, а {', '.join(bad)}: мажоры должны совпадать")
    # ----------------------------------------------------------------------
    # ЧТО ИЗМЕНЕНО (1.2): README.md — единый вход; его кнопка «Открыть в Colab» должна вести на проверяемый ноутбук
    # ПОЧЕМУ: my-FT Р-10 — продуктив = main; ссылка на другой файл — пользователь запустит не то
    # ----------------------------------------------------------------------
    links = set(re.findall(r"blob/main/(RepSSPR[\w.]*\.ipynb)", read("README.md"))) if os.path.exists("README.md") else set()
    if links != {NOTEBOOK_FILE}:
        raise Fail(f"README.md ведёт на {', '.join(sorted(links)) or 'ничего'}, а ноутбук — {NOTEBOOK_FILE}: поправьте ссылки в README.md")
    return f"{NOTEBOOK_FILE} ({nb_ver}) + {MODULE_FILE} {rv.VERSION} + {TEMPLATE_FILE} {tpl_ver}"

SCENARIOS = [
    ("а", "демо-выгрузка → отчёт совпадает с макетом", scen_a),
    ("б", "боевая выгрузка → отчёт ноутбука = прямая сборка модулем", scen_b),
    ("в", "сбои модели → отчёт собирается, повторы срабатывают", scen_v),
    ("г", "Диск и повтор недели из кэша → 0 вызовов, тот же отчёт", scen_g),
    ("д", "чужой мажор шаблона, нет модуля → остановка в ячейке 1", scen_d),
    ("е", "модуль и шаблон с GitHub, GitHub недоступен → запасная копия или остановка", scen_e),
    ("ж", "локальный запуск без Colab → отчёт; нет прокси → остановка; ключ из .env", scen_zh),
]


def main():
    global TMP
    TMP = tempfile.mkdtemp(prefix="selftest_")
    t_all = time.time()
    print(f"Стенд самопроверки ({VERSION}): ноутбук на подставной модели, токенов 0")
    try:
        print("Проверяется: " + preflight())
    except Exception as e:                        # Fail — расхождение версий; прочее — модуль или шаблон не читаются
        print(f"[СБОЙ] версии и файлы: {e if isinstance(e, Fail) else f'{type(e).__name__}: {e}'}\n"
              f"ИТОГ: СБОЙ — до прогонов не дошло")
        shutil.rmtree(TMP, ignore_errors=True)
        return 1
    failed = 0
    for key, title, fn in SCENARIOS:
        t0 = time.time()
        try:
            note = fn()
            print(f"[ОК]   {key}) {title} ({time.time() - t0:.1f} с)\n       {note}")
        except Fail as e:
            failed += 1
            print(f"[СБОЙ] {key}) {title} ({time.time() - t0:.1f} с)\n       {e}")
        except Exception as e:
            failed += 1
            print(f"[СБОЙ] {key}) {title}\n       ошибка самого стенда: {type(e).__name__}: {e}")
    if failed:
        print(f"ИТОГ: СБОЙ — не прошли {failed} из {len(SCENARIOS)}. Рабочая папка: {TMP}")
        return 1
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"ИТОГ: ОК — {len(SCENARIOS)} из {len(SCENARIOS)} за {time.time() - t_all:.0f} с")
    return 0


if __name__ == "__main__":
    sys.exit(main())
