from screen_watch_assistant.models import ALLOWED_PROMPTS
from screen_watch_assistant.recognizer import PromptRecognizer


def test_allowed_prompt_list_is_narrow_and_stable() -> None:
    assert "继续观看" in ALLOWED_PROMPTS
    assert "提交" not in ALLOWED_PROMPTS
    assert "删除" not in ALLOWED_PROMPTS


def test_normalize_removes_spaces_and_ignores_case() -> None:
    assert PromptRecognizer._normalize(" Continue  Watching ") == "continuewatching"


def test_body_sentence_is_not_an_exact_prompt() -> None:
    assert PromptRecognizer._is_exact_prompt("继续播放", "继续播放")
    assert not PromptRecognizer._is_exact_prompt("为了继续播放，请确认你仍在观看", "继续播放")
