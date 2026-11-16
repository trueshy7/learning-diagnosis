"""后续真实模型适配的接口边界；当前流程不引用或实例化它。"""

from typing import Protocol


class LLMClient(Protocol):
    async def generate(self, *, system: str, user: str) -> str:
        """未来实现时须统一超时、输出校验及失败处理。"""
        ...


class UnimplementedLLMClient:
    async def generate(self, *, system: str, user: str) -> str:
        raise NotImplementedError("当前骨架未接入真实 LLM，请先实现并验证独立适配器。")

