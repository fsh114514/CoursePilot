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


def _tesseract_data(words):
    """构造 tesseract image_to_data 的 DICT 结构（同行 word）。"""
    n = len(words) + 4  # 前 4 行是空的行头
    return {
        "text": [""] * 4 + [w for w, *_ in words],
        "block_num": [1] * n,
        "par_num": [1] * n,
        "line_num": [1] * n,
        "left": [0] * 4 + [w[1] for w in words],
        "top": [0] * 4 + [w[2] for w in words],
        "width": [0] * 4 + [w[3] for w in words],
        "height": [0] * 4 + [w[4] for w in words],
        "conf": [-1] * 4 + [w[5] for w in words],
    }


def test_tesseract_split_words_are_matched_across_line() -> None:
    """tesseract 把「我还在看」拆成 4 个独立 word 时，也要能识别。"""
    r = PromptRecognizer(("我还在看",))
    data = _tesseract_data([
        ("我", 23, 24, 72, 42, 96),
        ("还", 119, 22, 22, 44, 96),
        ("在", 140, 18, 43, 67, 96),
        ("看", 182, 24, 28, 43, 96),
    ])
    match = r._match_from_tesseract_data(data, 1.0, 1.0)
    assert match is not None
    assert match.text == "我还在看"
    assert match.confidence >= 0.75


def test_tesseract_prompt_in_sentence_gets_center() -> None:
    """提示词嵌在一句话中间时，返回的是提示词本身的中心点。"""
    r = PromptRecognizer(("继续观看",))
    data = _tesseract_data([
        ("请", 10, 10, 20, 20, 95),
        ("继续", 40, 10, 40, 20, 95),
        ("观看", 85, 10, 40, 20, 95),
        ("课程", 130, 10, 40, 20, 95),
    ])
    match = r._match_from_tesseract_data(data, 1.0, 1.0)
    assert match is not None
    assert match.text == "继续观看"
    # 「继续观看」覆盖 left=40..125，中心 x≈82.5
    assert 70 < match.center_x < 95


def _windows_ocr_lines():
    """模拟 Windows OCR 返回的整行数据（含 words 边界框）。"""
    return [
        {
            "text": "你 还 在 观 看 吗 ？",
            "words": [
                {"text": "你", "x": 502, "y": 471, "w": 27, "h": 25},
                {"text": "还", "x": 530, "y": 471, "w": 26, "h": 25},
                {"text": "在", "x": 557, "y": 471, "w": 26, "h": 25},
                {"text": "观", "x": 584, "y": 472, "w": 26, "h": 24},
                {"text": "看", "x": 612, "y": 471, "w": 25, "h": 25},
                {"text": "吗", "x": 640, "y": 472, "w": 24, "h": 24},
                {"text": "？", "x": 666, "y": 473, "w": 13, "h": 21},
            ],
        },
        {
            "text": "我 还 在 看",
            "words": [
                {"text": "我", "x": 562, "y": 583, "w": 17, "h": 18},
                {"text": "还", "x": 580, "y": 583, "w": 17, "h": 17},
                {"text": "在", "x": 598, "y": 583, "w": 17, "h": 17},
                {"text": "看", "x": 616, "y": 583, "w": 17, "h": 18},
            ],
        },
    ]


def test_windows_ocr_matches_button_text() -> None:
    """Windows OCR 识别出「我还在看」按钮时能匹配并定位中心。"""
    r = PromptRecognizer(("我还在看",))
    # 模拟 win_ocr
    class FakeWinOCR:
        available = True
        def recognize(self, image):
            return _windows_ocr_lines()
    r.win_ocr = FakeWinOCR()
    match = r._find_with_windows_ocr(None, 1.0, 1.0)
    assert match is not None
    assert match.text == "我还在看"
    # 按钮 words 覆盖 x=562..633，y=583..601，中心 ≈ (597.5, 592)
    assert 590 < match.center_x < 605
    assert 585 < match.center_y < 600
