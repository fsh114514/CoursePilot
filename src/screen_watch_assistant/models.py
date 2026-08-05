from dataclasses import dataclass


@dataclass(frozen=True)
class Window:
    id: int
    title: str
    owner: str


@dataclass(frozen=True)
class TextMatch:
    text: str
    confidence: float
    center_x: float
    center_y: float


ALLOWED_PROMPTS = (
    "我还在看",
    "继续观看",
    "继续播放",
    "仍在观看",
    "are you still watching",
    "continue watching",
    "resume",
)

BLOCKED_PROMPT_WORDS = (
    "提交", "交卷", "支付", "购买", "删除", "清空", "确认订单",
    "submit", "pay", "purchase", "delete", "remove",
)
