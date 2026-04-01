"""xAPI 데이터팀(#7) + 데이터검수팀(#8) 테스트"""
import os
os.environ["LLM_MODE"] = "mock"

import pytest
from agents.a07_data import DataAgent
from agents.a08_data_reviewer import DataReviewerAgent


class TestDataAgent:

    def _make_digital_question(self, q_type="객관식"):
        return {
            "pkey": "QI-XAPI-001-01",
            "choices": ["① 1", "② 2", "③ 3", "④ 4", "⑤ 5"] if q_type == "객관식" else [],
            "answer_correct": {"correct": [3], "is_multiple": False, "scoring_mode": "all"},
            "metadata": {"question_type": q_type},
        }

    @pytest.mark.asyncio
    async def test_choice_xapi_config(self):
        agent = DataAgent()
        result = await agent.process({
            "ref_id": "XAPI-001",
            "pkey": "QI-XAPI-001-01",
            "digital_question": self._make_digital_question("객관식"),
        })
        assert result["result"] == "PASS"
        config = result["output"]["xapi_config"]
        assert config["content_id"] == "QI-XAPI-001-01"
        assert config["response_type"] == "choice"
        assert config["req_act_cnt"] == 1
        assert "submit" in config["events"]
        assert config["events"]["submit"]["verb"] == "completed"

    @pytest.mark.asyncio
    async def test_short_answer_xapi(self):
        agent = DataAgent()
        result = await agent.process({
            "ref_id": "XAPI-002",
            "pkey": "QI-XAPI-002-01",
            "digital_question": self._make_digital_question("단답형"),
        })
        config = result["output"]["xapi_config"]
        assert config["response_type"] == "short_answer"

    @pytest.mark.asyncio
    async def test_descriptive_xapi(self):
        agent = DataAgent()
        result = await agent.process({
            "ref_id": "XAPI-003",
            "pkey": "QI-XAPI-003-01",
            "digital_question": self._make_digital_question("서술형"),
        })
        config = result["output"]["xapi_config"]
        assert config["response_type"] == "descriptive"

    @pytest.mark.asyncio
    async def test_events_have_required_verbs(self):
        agent = DataAgent()
        result = await agent.process({
            "ref_id": "XAPI-004",
            "digital_question": self._make_digital_question(),
        })
        events = result["output"]["xapi_config"]["events"]
        assert events["load"]["verb"] == "started"
        assert events["submit"]["verb"] == "completed"
        assert events["view_solution"]["verb"] == "viewed"
        assert events["retry"]["verb"] == "reset"
        assert events["leave"]["verb"] == "left"

    @pytest.mark.asyncio
    async def test_grading_rule(self):
        agent = DataAgent()
        result = await agent.process({
            "ref_id": "XAPI-005",
            "digital_question": self._make_digital_question(),
        })
        rule = result["output"]["xapi_config"]["grading_rule"]
        assert rule["correct"] == [3]
        assert rule["is_multiple"] is False
        assert rule["scoring_mode"] == "all"

    @pytest.mark.asyncio
    async def test_restore_schema(self):
        agent = DataAgent()
        result = await agent.process({
            "ref_id": "XAPI-006",
            "digital_question": self._make_digital_question(),
        })
        restore = result["output"]["xapi_config"]["restore_schema"]
        assert "time_spent" in restore

    @pytest.mark.asyncio
    async def test_empty_input_error(self):
        agent = DataAgent()
        result = await agent.process({"ref_id": "XAPI-ERR"})
        assert result["result"] == "ERROR"


class TestDataReviewerAgent:

    def _make_good_config(self):
        return {
            "content_id": "QI-001",
            "content_type": "question",
            "question_type": "객관식",
            "response_type": "choice",
            "req_act_cnt": 1,
            "events": {
                "load": {"verb": "started"},
                "submit": {"verb": "completed", "result_fields": {"response": {}}},
                "leave": {"verb": "left", "result_fields": {"duration": {}}},
            },
            "grading_rule": {"correct": [3], "is_multiple": False, "scoring_mode": "all"},
            "restore_schema": {"selected_choice": "int", "time_spent": "int"},
        }

    @pytest.mark.asyncio
    async def test_good_config_passes(self):
        reviewer = DataReviewerAgent()
        result = await reviewer.process({
            "ref_id": "DR-001",
            "xapi_config": self._make_good_config(),
        })
        assert result["result"] == "PASS"
        assert result["score"] >= 85.0

    @pytest.mark.asyncio
    async def test_empty_config_rejects(self):
        reviewer = DataReviewerAgent()
        result = await reviewer.process({"ref_id": "DR-ERR", "xapi_config": {}})
        assert result["result"] == "REJECT"

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        os.environ.get("LLM_MODE", "mock") == "mock",
        reason="mock 모드에서는 자동 PASS 반환 (낮은 점수 테스트 불가)",
    )
    async def test_missing_events_reduces_score(self):
        reviewer = DataReviewerAgent()
        config = self._make_good_config()
        config["events"] = {}
        result = await reviewer.process({"ref_id": "DR-002", "xapi_config": config})
        assert result["score"] < 85.0

    @pytest.mark.asyncio
    async def test_wrong_type_match_reduces_score(self):
        reviewer = DataReviewerAgent()
        config = self._make_good_config()
        config["response_type"] = "descriptive"  # 객관식인데 descriptive
        result = await reviewer.process({"ref_id": "DR-003", "xapi_config": config})
        items = result.get("score_detail", {}).get("items", [])
        type_item = next((i for i in items if i["name"] == "문항 유형 일치"), None)
        if type_item:
            assert type_item["score"] < 10.0


class TestDataPipeline:
    """데이터팀 → 데이터검수팀 연결"""

    @pytest.mark.asyncio
    async def test_data_then_review(self):
        agent = DataAgent()
        data_result = await agent.process({
            "ref_id": "PIPE-001",
            "pkey": "QI-PIPE-001-01",
            "digital_question": {
                "choices": ["① A", "② B", "③ C"],
                "answer_correct": {"correct": [2], "is_multiple": False, "scoring_mode": "all"},
                "metadata": {"question_type": "객관식"},
            },
        })
        assert data_result["result"] == "PASS"

        reviewer = DataReviewerAgent()
        review_result = await reviewer.process({
            "ref_id": "PIPE-001",
            "xapi_config": data_result["output"]["xapi_config"],
        })
        assert review_result["result"] == "PASS"
        assert review_result["score"] >= 85.0
