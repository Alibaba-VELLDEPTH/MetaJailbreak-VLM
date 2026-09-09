import base64
import io
import time
from io import BytesIO
from typing import Any, List, Optional, Tuple
import requests
from requests.adapters import HTTPAdapter
from PIL import Image


class VLMChatClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        max_retries: int = 2,
        default_system_prompt: str = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_retries = max_retries
        self.session = requests.Session()
        adapter = HTTPAdapter(pool_connections=5, pool_maxsize=10)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.default_system_prompt = default_system_prompt

    def __call__(self, prompt: str, **kwargs) -> str:
        sys_prompt = (
            self.default_system_prompt
            if self.default_system_prompt
            else "You are a helpful AI assistant."
        )
        return self.generate(system_prompt=sys_prompt, user_instruction=prompt)

    def generate(self, system_prompt: str, user_instruction: str) -> str:
        history = [{"role": "system", "content": system_prompt}]

        response_text, _ = self.chat(
            prompt=user_instruction, image=None, history=history
        )
        return response_text

    def chat(
        self,
        prompt: Optional[str] = None,
        image: Optional[Image.Image] = None,
        history: List = None,
        messages: Optional[List] = None,
    ) -> Tuple[str, List]:
        """
        支援兩種傳參方式：
        1. 直接傳入標準的 OpenAI 格式的 messages 列表。
        2. 傳入 prompt, image 和 history 自動組合。
        """

        if messages is not None:
            final_messages = messages
        else:
            final_messages = (history or [])[:]
            content = []

            if image:
                buffered = BytesIO()
                if image.mode != "RGB":
                    image = image.convert("RGB")
                image.save(buffered, format="JPEG")
                img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_str}"},
                    }
                )

            if prompt:
                content.append({"type": "text", "text": prompt})

            final_messages.append({"role": "user", "content": content})

        payload = {"model": self.model, "messages": final_messages, "max_tokens": 4096}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"

        for attempt in range(self.max_retries + 1):
            try:
                resp = self.session.post(
                    url, headers=headers, json=payload, timeout=300
                )
                if resp.status_code == 200:
                    data = resp.json()
                    try:
                        return data["choices"][0]["message"]["content"], final_messages
                    except (KeyError, IndexError):
                        return f"Error Parsing JSON: {data}", final_messages
                elif resp.status_code == 400:
                    return "I cannot assist with that (API Filtered).", final_messages
                else:
                    print(f"[API Error] {resp.status_code}: {resp.text}")
            except Exception as e:
                print(f"[Request Failed]: {e}")
                time.sleep(1)

        return "Error: API Request Failed", final_messages


class ImageGenerationClient:
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    @staticmethod
    def _dashscope_size(size: str) -> str:
        return size.replace("x", "*")

    def generate(
        self, prompt: str, size="720x1280", steps=50, cfg=4.0
    ) -> Tuple[Optional[str], Any]:
        """Generate an image using DashScope native or OpenAI-compatible APIs."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # z-image-turbo is exposed through DashScope's native multimodal API;
        # the compatible-mode endpoint currently returns 404 for image generation.
        if "dashscope.aliyuncs.com" in self.base_url and self.model == "z-image-turbo":
            url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
            payload = {
                "model": self.model,
                "input": {
                    "messages": [
                        {
                            "role": "user",
                            "content": [{"text": prompt}],
                        }
                    ]
                },
                "parameters": {
                    "size": self._dashscope_size(size),
                    "n": 1,
                },
            }
        else:
            url = f"{self.base_url}/images/generations"
            payload = {
                "model": self.model,
                "prompt": prompt,
                "n": 1,
                "size": size,
                "response_format": "b64_json",
                "extra_body": {
                    "num_inference_steps": steps,
                    "guidance_scale": cfg,
                },
            }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=300)
            if resp.status_code != 200:
                print(f"[Gen Error] Status: {resp.status_code}, Msg: {resp.text}")
                try:
                    return None, resp.json()
                except Exception:
                    return None, {"status": resp.status_code, "text": resp.text}

            result = resp.json()
            if "data" in result and result["data"]:
                data_item = result["data"][0]
                return data_item.get("b64_json") or data_item.get("url"), result

            choices = result.get("output", {}).get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", [])
                for item in content:
                    if isinstance(item, dict) and item.get("image"):
                        return item["image"], result
            return None, result
        except Exception as e:
            print(f"[Image Gen Exception]: {e}")
            return None, {}


class ImageEditClient:
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key

        self.base_url = base_url.rstrip("/")
        self.model = model

    def edit(
        self, prompt: str, image: Image.Image, size="1024x1024"
    ) -> Tuple[Optional[str], Any]:
        """
        输入:
            prompt: 编辑指令 (例如: "将裙子改成白色")
            image: PIL Image 对象 (来自你的 Parquet 数据)
        输出:
            (图片URL/或Base64数据, 原始响应对象)
        """
        url = f"{self.base_url}/images/edits"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        img_byte_arr = io.BytesIO()

        image.save(img_byte_arr, format="PNG")
        img_byte_arr.seek(0)

        files = {"image": ("input.png", img_byte_arr, "image/png")}
        data = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "response_format": "b64_json",
        }

        try:
            resp = requests.post(
                url, headers=headers, files=files, data=data, timeout=300
            )

            if resp.status_code == 200:
                result = resp.json()
                if "data" in result and len(result["data"]) > 0:
                    return result["data"][0].get("url") or result["data"][0].get(
                        "b64_json"
                    ), result
                else:
                    return None, result
            else:
                print(f"[Edit Error] Status: {resp.status_code}, Msg: {resp.text}")
                return None, resp.json()
        except Exception as e:
            print(f"[Image Edit Exception]: {e}")
            return None, {}
