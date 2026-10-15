# ----------------------------------------------------------------------
# extract_ai_stub.py — текст ИИ из готового отчёта → examples/ai_stub_w41.json (заглушка ИИ, режим 3)
# ЧТО: разовый извлекатель: из HTML готового отчёта берёт разборы слайдов (summary, items, decisions, root_all,
#      root, notsolved, fix_first, nsi_nonedit, best, врезки notes) и скрытые повторы (signals) — в схеме разметки ИИ
#      (data.md, разд. 11). Цифры — уже текстом, номера обращений — той недели.
# ПОЧЕМУ: my-FT Т-113 — макет и отчёт с заглушкой ИИ 3 показывают реалистичный текст без вызова модели;
#         текст берётся один раз и дальше просто подставляется.
# Запуск (Linux / Bash):  python3 tools/extract_ai_stub.py "result/Отчет по качеству W41 (05.10.2026) (1).html"
# Windows (PowerShell):   py tools\extract_ai_stub.py "result\Отчет по качеству W41 (05.10.2026) (1).html"
# ----------------------------------------------------------------------
VERSION = "1.0"
OUT_FILE = "examples/ai_stub_w41.json"

import html, json, os, re, sys

ID_RX = re.compile(r"\d{2}-\d{8}")
uniq = lambda h: list(dict.fromkeys(ID_RX.findall(h)))          # номер в ячейке встречается дважды (ссылка и data-tid)


KEYS_LEFT = []                       # ключи {метрика}, оставшиеся в готовом отчёте неподставленными


def text(h):
    t = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", h)).split())
    # в W41 колонка «Проблема» решений руководителя выведена без подстановки цифр — ключ показывается как «—»
    KEYS_LEFT.extend(re.findall(r"\{(\w+)\}", t))
    return re.sub(r"\{\w+\}", "—", t)


def rows(sec):
    """Строки tbody панели → список списков HTML ячеек."""
    m = re.search(r"<tbody>(.*?)</tbody>", sec, re.S)
    return [re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S) for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S)] if m else []


def split_ids(cell):
    """Ячейка «факт» с номерами в <div class=ids> → (текст, номера)."""
    m = re.search(r'<div class="?ids"?>', cell)
    i = m.start() if m else -1
    return (text(cell[:i]), uniq(cell[i:])) if i >= 0 else (text(cell), [])


def first_id(cell):
    m = ID_RX.search(cell)
    return m.group(0) if m else ""


def main(src):
    s = open(src, encoding="utf-8").read()
    week = re.search(r"<title>.*?Неделя (\d+)</title>", s)
    out = {"meta": {"source": f"W{week.group(1) if week else '?'} — {os.path.basename(src)}", "version": VERSION},
           "slides": {}, "signals": []}
    for key, art in re.findall(r'<article class="slide" id="(s\d+)">(.*?)</article>', s, re.S):
        sl = {}
        for sec in re.findall(r'<section class="panel[^"]*">.*?</section>', art, re.S):
            h = re.search(r"<h3>(.*?)</h3>", sec, re.S)
            h = text(h.group(1)) if h else ""
            R = rows(sec)
            if h.startswith("✦ Разбор ИИ по слайду"):
                m = re.search(r'<p class="ai-sum">(.*?)</p>', sec, re.S)
                sl["summary"] = text(m.group(1)) if m else ""
                sl["items"] = [dict(zip(("fact", "ids"), split_ids(c[0])), conc=text(c[1]), act=text(c[2]), who=text(c[3]),
                                    eff="" if text(c[4]) == "—" else text(c[4])) for c in R if len(c) >= 5]
            elif h.startswith("Что требует решения руководителя"):
                sl["decisions"] = [dict(zip(("fact", "ids"), split_ids(c[1])), problem=text(c[0]), act=text(c[2]), who=text(c[3]),
                                        eff=text(c[4])) for c in R if len(c) >= 5]
            elif h.startswith("Первопричины недели"):
                sl["root_all"] = [{"cause": text(c[0]), "ids": uniq(c[1]), "act": text(c[2]), "who": text(c[3])} for c in R if len(c) >= 4]
            elif h.startswith("Общие первопричины"):
                sl["root"] = [{"cause": text(c[0]), "ids": uniq(c[1]), "fix": text(c[2]), "kind": text(c[3])} for c in R if len(c) >= 4]
            elif h.startswith("Закрыто, но не решено"):
                sl["notsolved"] = [{"id": first_id(c[0]), "done": text(c[1]), "why": text(c[2]), "risk": text(c[3])} for c in R if len(c) >= 4]
            elif h.startswith("Что чинить первым"):
                sl["fix_first"] = [{"name": text(c[0]), "ids": uniq(c[-1]), "act": text(c[-2])} for c in R if len(c) >= 6]
            elif h.startswith("НСИ отдельно"):
                sl["nsi_nonedit"] = [{"id": first_id(c[0]), "cls": text(c[2]), "note": text(c[3])} for c in R if len(c) >= 4]
            elif h.startswith("Лучшие решения"):
                sl["best"] = [{"id": first_id(c[0]), "why": text(c[2]), "kb": text(c[3])} for c in R if len(c) >= 4]
            elif h.startswith("Скрытые повторы"):
                out["signals"] = [{"id": first_id(c[0]), "q": text(c[1]).strip("«»"), "k": text(c[2]), "a": text(c[3])} for c in R if len(c) >= 4]
        notes = [text(n) for n in re.findall(r'<div class="ai-note"><i>✦</i><div>(.*?)</div></div>', art, re.S)]
        if key == "s1" and notes:
            sl["notes"] = dict(zip(("flow", "weeks", "history"), notes))
        if sl:
            out["slides"][key] = sl
    js = json.dumps(out, ensure_ascii=False, indent=1)
    # фигурные скобки в тексте модуль принял бы за ключи метрик — в готовом отчёте их быть не должно
    if re.search(r"\{\w+\}", json.dumps(out["slides"], ensure_ascii=False)):
        sys.exit("в тексте отчёта есть {ключ} — такой текст для заглушки не годится")
    open(OUT_FILE, "w", encoding="utf-8").write(js)
    n = {k: {f: len(v) if isinstance(v, (list, dict)) else 1 for f, v in sl.items()} for k, sl in out["slides"].items()}
    print(f"Записан {OUT_FILE}: источник {out['meta']['source']}; повторов {len(out['signals'])}; слайды {n}")
    if KEYS_LEFT:
        print(f"Неподставленные ключи в отчёте заменены на «—»: {sorted(set(KEYS_LEFT))}")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if len(sys.argv) != 2:
        sys.exit("укажите HTML готового отчёта")
    main(sys.argv[1])
