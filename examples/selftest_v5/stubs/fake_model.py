# ----------------------------------------------------------------------
# fake_model.py — подставная модель стенда самопроверки (examples/selftest_v5)
# ЧТО: вместо DeepSeek / Gemini отвечает разметкой макета (файл из переменной окружения NB_AI_FILE —
#      examples/mockup_v2_ai.json). Этап узнаётся по первой строке системного промпта («ЗАДАЧА: …»).
#      FAIL_MODE=errors — сбои для проверки повторов: обрыв JSON, негодная строка, чужой номер, неизвестный ключ метрики,
#      ответ не JSON. Неизвестный этап — ошибка: новый этап в ноутбуке требует ответа и здесь.
# ПОЧЕМУ: my-FT Т-72 — проверка ноутбука без ключей, сети и токенов
# ----------------------------------------------------------------------
import asyncio, json, os, re

AI = json.load(open(os.environ["NB_AI_FILE"], encoding="utf-8"))
T = {a["id"]: a for a in AI["tickets"]}
O = {a["id"]: a for a in AI["open_old"]}
FAIL = os.environ.get("FAIL_MODE", "")
LOG = []        # (этап, модель, response_format, max_tokens) — по каждому вызову
_seen = {}


def once(tag):
    """True при первом обращении с этим тегом: сбой случается один раз, повтор должен его исправить."""
    _seen[tag] = _seen.get(tag, 0) + 1
    return _seen[tag] == 1


async def answer(model, messages, **kw):
    await asyncio.sleep(0)
    system, user = messages[0]["content"], messages[1]["content"]
    stage = system.split("\n", 1)[0]
    LOG.append((stage, model, kw.get("response_format"), kw.get("max_tokens")))
    if "РАЗМЕТКА РЕШЁННЫХ" in stage:
        ids = re.findall(r"^ID: (\d{2}-\d{8})", user, re.M)
        if FAIL == "errors" and len(ids) > 7 and once("trunc"):
            return '{"results": [{"id": "' + ids[0] + '", "g": "обрыв'           # обрыв JSON — пачка заново меньшим размером
        rows = [dict(T[i]) for i in ids if i in T]
        if FAIL == "errors" and rows and once("bad_row"):
            rows[0]["st"] = "XYZ"                                                  # негодная строка — на повтор
        return json.dumps({"results": rows}, ensure_ascii=False)
    if "ГРУППЫ ТЕМ" in stage:
        if "нарушают правило 4" in user:                                           # второй проход: новые названия групп
            names = re.findall(r"^\d+\. (.+?) — темы:", user, re.M)
            return json.dumps({"names": names}, ensure_ascii=False)
        topics = re.findall(r"^(\d+)\. (.+?) — суть:", user, re.M)
        return json.dumps({"groups": [{"name": t, "items": [int(n)]} for n, t in topics]}, ensure_ascii=False)
    if "СТАРЫЕ ОТКРЫТЫЕ" in stage:
        ids = re.findall(r"^ID: (\d{2}-\d{8})", user, re.M)
        return json.dumps({"results": [O[i] for i in ids if i in O]}, ensure_ascii=False)
    if "КРИТИЧНЫЕ ОТКРЫТЫЕ" in stage:
        lst = list(AI["open_crit"])
        if FAIL == "errors" and once("crit"):
            lst = lst + [{"id": "00-99999999", "why": "выдумка"}]                  # номер не из выгрузки — повтор
        return json.dumps({"open_crit": lst}, ensure_ascii=False)
    if "ПЛАНШЕТАМ" in stage:
        return json.dumps({"planshet": AI["planshet"]}, ensure_ascii=False)
    if "СКРЫТЫЕ ПОВТОРЫ" in stage:
        return json.dumps({"signals": AI["signals"]}, ensure_ascii=False)
    if "РАЗБОР СЛАЙДА" in stage:
        key = re.search(r"\(ключ (s\d+)\)", user).group(1)
        s = json.loads(json.dumps(AI["slides"][key]))
        if FAIL == "errors" and key == "s3" and once("s3"):
            s["summary"] += " {нет_такой_метрики}"                                 # неизвестный ключ — повтор с замечанием
        if FAIL == "errors" and key == "s8":
            return "это не JSON"                                                    # все попытки негодны — нейтральная строка
        return "```json\n" + json.dumps(s, ensure_ascii=False) + "\n```"
    raise ValueError("подставная модель не знает этап: " + stage)
