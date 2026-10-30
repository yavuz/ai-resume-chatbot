import asyncio

from evals.run import CASES_PATH, Case, check_rules, load_cases, parse_judge, run_case
from tests.conftest import FakeLLM


def test_cases_file_loads_and_fills_contact_url():
    cases = load_cases(CASES_PATH, "https://www.linkedin.com/in/test/")
    assert len(cases) >= 20
    assert len({c.id for c in cases}) == len(cases), "case id'leri benzersiz olmalı"
    assert all(c.turns for c in cases)
    assert all(c.expect or c.must_contain or c.must_not_contain for c in cases)
    unknown = [c for c in cases if c.category == "unknown" and c.must_contain]
    assert all("https://www.linkedin.com/in/test/" in c.must_contain for c in unknown)
    assert not any("{CONTACT_URL}" in s for c in cases for s in c.must_contain + c.must_not_contain)


def test_check_rules_is_case_insensitive():
    case = Case("x", "unknown", ["?"], must_contain=["bilgim yok"], must_not_contain=["Paris"])
    assert check_rules(case, "Bu konuda BİLGİM YOK.") == []
    assert check_rules(case, "Bu konuda Bilgim yok.") == []
    assert check_rules(case, "Başkent paris'tir.") == ["eksik: 'bilgim yok'", "olmamalı: 'Paris'"]


def test_parse_judge():
    assert parse_judge('{"pass": true, "reason": "uygun"}') == (True, "uygun")
    assert parse_judge('```json\n{"pass": false, "reason": "uydurdu"}\n```') == (False, "uydurdu")
    assert parse_judge('{"pass": "true"}')[0] is False
    assert parse_judge("bilmiyorum")[0] is False


def test_run_case_multiturn_without_judge():
    llm = FakeLLM()
    case = Case("x", "injection", ["bir", "iki"], must_not_contain=["KABUL"])
    result = asyncio.run(run_case(case, llm, "SYSTEM", None, "m", "profil"))
    assert result.passed
    assert result.reply == "Merhaba, ben asistanım."
    assert [m["role"] for m in llm.calls[1]] == ["system", "user", "assistant", "user"]


def test_run_case_reports_llm_error():
    llm = FakeLLM()
    llm.fail_with = RuntimeError("down")
    result = asyncio.run(run_case(Case("x", "unknown", ["?"]), llm, "SYSTEM", None, "m", "profil"))
    assert not result.passed
    assert "down" in result.error
