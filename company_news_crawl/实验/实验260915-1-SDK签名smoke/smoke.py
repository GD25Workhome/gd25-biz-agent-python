"""
SDK 0.2.152 签名 smoke。

用与 backend/domain/news_crawl/agent_runner.py 完全相同的参数形状
构造 ClaudeAgentOptions,再真起一次 CLI 跑最小对话。

验证点:
  1. 构造参数签名兼容(不抛 TypeError / ValidationError)
  2. CLI 子进程模型能跑通,ResultMessage 正常返回
"""
import asyncio

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, ResultMessage


async def main() -> None:
    # ── 复刻 agent_runner.py 的构造(最小对话,不带 MCP 工具) ──
    options = ClaudeAgentOptions(
        system_prompt="你是测试助手。只回复 OK 两个字,不要说别的。",
        model=None,  # 与 agent_runner 一致:None → CLI 读环境变量 ANTHROPIC_MODEL
        # ⚠️ 不能传 None:SDK 0.2.152 connect 时做 **options.env,env=None 会抛
        #   TypeError: 'NoneType' object is not a mapping(subprocess_cli.py:811)
        env={},
        mcp_servers={},
        allowed_tools=[],
        disallowed_tools=["Bash", "WebFetch", "WebSearch", "Read", "Write", "Edit"],
        permission_mode="bypassPermissions",
        max_turns=3,
        skills=[],
        setting_sources=[],
    )
    print("✓ ClaudeAgentOptions 构造通过(签名兼容)")

    result = None
    async with ClaudeSDKClient(options=options) as client:
        await client.query("ping")
        async for msg in client.receive_response():
            if isinstance(msg, ResultMessage):
                result = msg

    if result is None:
        raise SystemExit("✗ 未收到 ResultMessage")

    print(
        f"✓ CLI 子进程对话跑通: subtype={result.subtype} "
        f"turns={result.num_turns} cost_usd={result.total_cost_usd} "
        f"is_error={result.is_error}"
    )
    if result.is_error:
        raise SystemExit("✗ ResultMessage.is_error=True")
    print("✓ 签名 smoke 全部通过")


if __name__ == "__main__":
    asyncio.run(main())
