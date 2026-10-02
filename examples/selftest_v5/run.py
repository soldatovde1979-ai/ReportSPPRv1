# ----------------------------------------------------------------------
# run.py — стенд самопроверки ReportSPPR v5: ноутбук целиком на подставной модели — без ключей, сети и токенов
# ЧТО: прогоняет ноутбук (ячейки как есть, exec_notebook.py) в пяти сценариях и сверяет отчёт:
#      а) демо-выгрузка → отчёт = макет examples/mockup_report_v2.html, кроме известных отличий; лог в Sheets пишется;
#      б) боевая выгрузка → отчёт ноутбука = прямая сборка модулем, кроме журнала ИИ;
#      в) сбои модели (обрыв JSON, негодная строка, чужой номер, неизвестный ключ, не-JSON) → отчёт собирается, повторы есть;
#      г) Диск: модуль и шаблон найдены в папке проекта (src/), история записана; повтор → 0 вызовов, тот же отчёт;
#      д) шаблон чужого мажора, нет модуля → остановка в ячейке 1, до вызовов модели.
# ПОЧЕМУ: my-FT Т-72 — «единый тест сэкономит деньги и время»: правка проверяется за секунды, а не боевым прогоном
#         (02.10 — 608 тыс. токенов). Качество ответов настоящей модели стенд не проверяет — только боевой прогон.
# Запуск из любой папки:  Linux / Bash — python3 examples/selftest_v5/run.py
#                         Windows / PowerShell — py examples\selftest_v5\run.py
# Нужно: Python 3.10+ и jinja2. В проект ничего не пишет: работа — во временной папке, при успехе она удаляется.
# Итог: «ИТОГ: ОК» и код возврата 0; иначе — что разошлось, код 1 и путь к рабочей папке (вывод ноутбука — stdout.txt).
# ----------------------------------------------------------------------
VERSION = "1.0"
STAND_MAJOR = 5                                   # стенд для мажора 5: ноутбук, модуль и шаблон — 5.x
NOTEBOOK_FILE = "RepSSPR_v5.1.ipynb"              # проверяемый ноутбук; вышел новый номер — поправить здесь (стенд напомнит)
MODULE_FILE = "src/report_v5.py"
TEMPLATE_FILE = "template_v5.html"
MOCKUP_FILE = "examples/mockup_report_v2.html"    # эталон отчёта: макет собирает тот же модуль (build_mockup_v2.py)
AI_FILE = "examples/mockup_v2_ai.json"            # ответы подставной модели — разметка макета
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
import difflib, glob, importlib.util, json, os, re, shutil, subprocess, tempfile, time

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
    spec = importlib.util.spec_from_file_location("report_v5", MODULE_FILE)
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


def run_nb(tag, dump, upload, drive="never", fail="", debug=False, seed=None, drive_from=None):
    """Один прогон ноутбука в папке TMP/tag. upload — файлы окна загрузки кроме выгрузки; seed(work) — подготовить Диск;
    drive_from — взять Диск из рабочей папки прошлого прогона (повтор недели)."""
    work = os.path.join(TMP, tag)
    os.makedirs(work)
    if drive_from:
        shutil.copytree(os.path.join(drive_from, "drive"), os.path.join(work, "drive"))
    if seed:
        seed(work)
    env = dict(os.environ, NB_UPLOAD=";".join(os.path.abspath(p) for p in [dump] + upload), NB_DRIVE=drive,
               NB_DEBUG="1" if debug else "0", NB_AI_FILE=os.path.abspath(AI_FILE), FAIL_MODE=fail,
               PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, os.path.join(HERE, "exec_notebook.py"), os.path.abspath(NOTEBOOK_FILE), work],
                       env=env, capture_output=True, timeout=900)
    out = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
    with open(os.path.join(work, "stdout.txt"), "w", encoding="utf-8") as f:
        f.write(out)
    res_file = os.path.join(work, "stand_result.json")
    r = json.load(open(res_file, encoding="utf-8")) if os.path.exists(res_file) else \
        {"ok": False, "cell": None, "error": "прогон оборвался до итога", "calls": {}, "downloads": [], "sheets": {}}
    reports = glob.glob(os.path.join(work, "result", "*.html"))
    r.update(out=out, work=work, html=read(reports[0]) if len(reports) == 1 else None)
    return r


def need_ok(r, what):
    if not r["ok"]:
        tail = "\n        ".join(r["out"].strip().splitlines()[-6:])
        raise Fail(f"{what}: ноутбук остановился в ячейке {r['cell']}: {r['error']}\n        {tail}")
    if r["html"] is None:
        raise Fail(f"{what}: отчёт не найден в {r['work']}/result")


TOOLS = [TEMPLATE_FILE, MODULE_FILE]              # «выбраны в окне загрузки» вместе с выгрузкой


def scen_a():
    r = run_nb("a", DEMO_DUMP, TOOLS, debug=True)
    need_ok(r, "прогон")
    try:
        expect_diffs(read(MOCKUP_FILE), r["html"], list(KNOWN_DIFFS), "отчёт против макета")
    except Fail as e:
        raise Fail(f"{e}\n        изменение задумано — пересоберите макет (python3 examples/build_mockup_v2.py), "
                   f"проверьте его diff и закоммитьте вместе с правкой; не задумано — ищите ошибку")
    logs, token = r["sheets"].get("Logs", []), r["sheets"].get("Token", [])
    if len(logs) != 2 or len(token) != 2 or len(token[1]) != len(token[0]):
        raise Fail(f"лог в Sheets (IS_DEBUG = 1): строк в Logs {len(logs)}, в Token {len(token)} — ждали заголовок и одну строку")
    return f"отчёт = макет, кроме {len(KNOWN_DIFFS)} известных отличий; лог в Sheets записан"


def scen_b():
    r = run_nb("b", REAL_DUMP, TOOLS)
    need_ok(r, "прогон")
    rv5 = load_module()
    R = rv5.load(json.load(open(REAL_DUMP, encoding="utf-8-sig")), os.path.basename(REAL_DUMP), None, [],
                 demo=False, say=lambda *a, **k: None)
    rv5.attach_ai(R, json.load(open(AI_FILE, encoding="utf-8")))
    expect_diffs(rv5.render(R, read(TEMPLATE_FILE)), r["html"], RUN_LOG_DIFFS, "отчёт ноутбука против прямой сборки модулем")
    STATE["b"] = r
    return "отчёт ноутбука = прямая сборка модулем, кроме журнала ИИ"


def scen_v():
    base = STATE.get("b")
    if not base:
        raise Fail("нет базы для сравнения вызовов — сценарий «б» не прошёл")
    r = run_nb("v", REAL_DUMP, TOOLS, fail="errors")
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


def scen_g():
    drive_root, history_dir = notebook_param("DRIVE_ROOT"), notebook_param("HISTORY_DIR")
    on_disk = lambda work, p: p.replace("/content", work.replace("\\", "/"))

    def seed(work):                               # папка проекта на Диске — как репозиторий: шаблон в корне, модуль в src/
        root = on_disk(work, drive_root)
        os.makedirs(os.path.join(root, "src"))
        shutil.copy(TEMPLATE_FILE, root)
        shutil.copy(MODULE_FILE, os.path.join(root, "src"))

    r1 = run_nb("g1", DEMO_DUMP, [], drive="always", seed=seed)
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
    text, n = re.subn(r'TEMPLATE_VERSION = "\d+\.\d+"', f'TEMPLATE_VERSION = "{STAND_MAJOR - 1}.9"', read(TEMPLATE_FILE), count=1)
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


def preflight():
    """Контроль версий до прогонов: стенд мажора STAND_MAJOR, ноутбук — последний, модуль и шаблон того же мажора."""
    found = []
    for p in glob.glob("RepSSPR_v*.ipynb"):
        m = re.fullmatch(r"RepSSPR_v(\d+)\.(\d+)\.ipynb", os.path.basename(p))
        if m:
            found.append(((int(m.group(1)), int(m.group(2))), os.path.basename(p)))
    if not os.path.exists(NOTEBOOK_FILE):
        raise Fail(f"нет {NOTEBOOK_FILE}" + (f"; в репозитории: {', '.join(n for _, n in sorted(found))}" if found else ""))
    newest = max(found)[1]
    if newest != NOTEBOOK_FILE:
        raise Fail(f"в репозитории есть {newest}, а стенд проверяет {NOTEBOOK_FILE}: поправьте NOTEBOOK_FILE в run.py"
                   + (f" или сделайте стенд selftest_v{max(found)[0][0]}" if max(found)[0][0] != STAND_MAJOR else ""))
    nb_ver = notebook_param("NOTEBOOK_VERSION")
    rv5 = load_module()
    tpl_ver = rv5.check_template(read(TEMPLATE_FILE))
    majors = {"ноутбук": nb_ver, "модуль": rv5.VERSION, "шаблон": tpl_ver}
    bad = [f"{k} {v}" for k, v in majors.items() if int(v.split(".")[0]) != STAND_MAJOR]
    if bad:
        raise Fail(f"стенд для мажора {STAND_MAJOR}, а {', '.join(bad)}")
    for name, path in (("MODULE_FILE", MODULE_FILE), ("TEMPLATE_FILE", TEMPLATE_FILE)):
        if notebook_param(name) != os.path.basename(path):
            raise Fail(f"ноутбук ищет {name} = {notebook_param(name)}, стенд подкладывает {os.path.basename(path)}")
    return f"{NOTEBOOK_FILE} ({nb_ver}) + {MODULE_FILE} {rv5.VERSION} + {TEMPLATE_FILE} {tpl_ver}"


SCENARIOS = [
    ("а", "демо-выгрузка → отчёт совпадает с макетом", scen_a),
    ("б", "боевая выгрузка → отчёт ноутбука = прямая сборка модулем", scen_b),
    ("в", "сбои модели → отчёт собирается, повторы срабатывают", scen_v),
    ("г", "Диск и повтор недели из кэша → 0 вызовов, тот же отчёт", scen_g),
    ("д", "чужой мажор шаблона, нет модуля → остановка в ячейке 1", scen_d),
]


def main():
    global TMP
    TMP = tempfile.mkdtemp(prefix="selftest_v5_")
    t_all = time.time()
    print(f"Стенд самопроверки v5 ({VERSION}): ноутбук на подставной модели, токенов 0")
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
