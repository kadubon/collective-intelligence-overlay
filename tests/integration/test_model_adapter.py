import httpx
from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from openai import AsyncOpenAI


async def test_real_provider_adapter_with_mock_http():
    seen = []

    def response(request):
        seen.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "id": "fixture",
                "object": "response",
                "created_at": 1,
                "model": "configured-test-model",
                "status": "completed",
                "output": [
                    {
                        "id": "m1",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "generated, not verified",
                                "annotations": [],
                            }
                        ],
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as http:
        async with AsyncOpenAI(
            api_key="fixture-not-a-secret", base_url="https://model.invalid/v1", http_client=http
        ) as sdk:
            agent = Agent(client=OpenAIChatClient(model="configured-test-model", async_client=sdk))
            output = await agent.run("test")
    assert output.text == "generated, not verified"
    assert seen == ["/v1/responses"]
