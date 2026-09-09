import base64
import io
import re


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def extract_prompts(response_text):
    results = {
        "thinking": "",
        "t2i_prompt": "",
        "anchor_prompt": "",
        "attack_prompt": "",
    }

    tags = {
        "thinking": r"\[THINKING\](.*?)\[/THINKING\]",
        "t2i_prompt": r"\[IMAGE_PROMPT\](.*?)\[/IMAGE_PROMPT\]",
        "anchor_prompt": r"\[ANCHOR_PROMPT\](.*?)\[/ANCHOR_PROMPT\]",
        "attack_prompt": r"\[ATTACK_PROMPT\](.*?)\[/ATTACK_PROMPT\]",
    }

    for key, pattern in tags.items():
        match = re.search(pattern, response_text, re.DOTALL | re.IGNORECASE)
        if match:
            content = match.group(1).strip()
            content = content.replace("**", "").strip('"').strip("'")
            results[key] = content

    return results


def pil_to_base64(pil_image, format="JPEG", quality=90):
    """
    将 PIL Image 对象转换为 base64 字符串

    :param pil_image: PIL.Image 对象
    :param format: 存储格式，建议使用 JPEG 以减小 Base64 字符串长度（针对 T2I 任务建议用 JPEG）
    :param quality: 压缩质量 (1-95)
    :return: base64 编码后的字符串
    """

    buffer = io.BytesIO()

    if pil_image.mode in ("RGBA", "P") and format.upper() == "JPEG":
        pil_image = pil_image.convert("RGB")

    pil_image.save(buffer, format=format, quality=quality)

    img_str = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return img_str
