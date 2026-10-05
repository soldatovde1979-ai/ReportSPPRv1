# ----------------------------------------------------------------------
# Заглушка openai для стенда самопроверки (examples/selftest_v5)
# ЧТО: AsyncOpenAI.chat.completions.create отвечает подставной моделью (fake_model.answer); токены — длина текста / 3,
#      чтобы журнал этапов и лог в Sheets заполнялись как в боевом прогоне.
# ----------------------------------------------------------------------
import fake_model


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Completions:
    async def create(self, **kw):
        text = await fake_model.answer(**kw)
        p = sum(len(m["content"]) for m in kw["messages"]) // 3
        c = len(text or "") // 3
        return _Obj(choices=[_Obj(message=_Obj(content=text))],
                    usage=_Obj(prompt_tokens=p, completion_tokens=c, total_tokens=p + c))


class AsyncOpenAI:
    def __init__(self, **kw):
        self.chat = _Obj(completions=_Completions())


class OpenAI(AsyncOpenAI):
    pass
