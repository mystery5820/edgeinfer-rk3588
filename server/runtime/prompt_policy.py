from __future__ import annotations


RK3588_FACTS_COMPACT = (
    "已知事实：RK3588 是瑞芯微 Rockchip 推出的高性能 AIoT SoC；"
    "采用四核 Cortex-A76 加四核 Cortex-A55 的 CPU 架构；"
    "内置 NPU，可用于端侧 AI 推理。"
)


RK3588_GUARDRAILS = (
    "不要把 RK3588 说成联发科、英伟达、高通或其他厂商推出的芯片；"
    "不要编造 4nm、5G、Wi-Fi 6E、Mali-G78、Mali-G710 等未给出的信息；"
    "不要复述规则或事实清单。"
)


RK3588_KEYWORDS = (
    "RK3588",
    "rk3588",
    "Rockchip",
    "rockchip",
    "瑞芯微",
    "端侧",
    "AIoT",
    "NPU",
)


def should_inject_rk3588_facts(prompt: str) -> bool:
    return any(keyword in prompt for keyword in RK3588_KEYWORDS)


def normalize_prompt_line(text: str) -> str:
    """
    rkllm_enhanced reads stdin line by line, so the final prompt must be a
    single line. Keep semantic separators but remove literal newlines.
    """
    return " ".join(text.replace("\r", " ").replace("\n", " ").split())


def build_serving_prompt(prompt: str) -> str:
    base_instruction = (
        "/no_think "
        "请只输出最终答案，不要输出思考过程、解释、注释或特殊符号；"
        "回答应简洁，优先控制在三句话以内；"
        "如果问题涉及硬件事实，只能基于已知事实回答。"
    )

    prompt = normalize_prompt_line(prompt)

    if should_inject_rk3588_facts(prompt):
        return normalize_prompt_line(
            base_instruction
            + " "
            + RK3588_FACTS_COMPACT
            + " "
            + RK3588_GUARDRAILS
            + " 用户问题："
            + prompt
        )

    return normalize_prompt_line(base_instruction + " 用户问题：" + prompt)
