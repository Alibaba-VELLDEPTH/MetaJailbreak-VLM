from dataclasses import dataclass


@dataclass
class AttackTrajectory:
    """记录攻击轨迹"""

    task_id: str
    instruction: str
    attacker_t2i_prompt: str
    anchor_prompt: str
    anchor_response: str
    victim_text_prompt: str
    victim_response: str
    score: float
    is_success: bool
    local_image_path: str
    guard_passed: bool = False
    guard_reason: str = "N/A"
    toxic_score: int = 1
    refusal_reason: str = "N/A"
