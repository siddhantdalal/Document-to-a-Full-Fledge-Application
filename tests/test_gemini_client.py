from unittest.mock import MagicMock, patch

from packages.ai_providers.base import CompletionRequest, Message
from packages.ai_providers.gemini_client import DEFAULT_MODEL, GeminiClient


def _mocked_response(text: str, usage: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.text = text
    response.model_dump.return_value = {
        "text": text,
        "usage_metadata": usage or {"prompt_token_count": 12, "candidates_token_count": 8},
    }
    return response


def test_complete_maps_messages_and_system_instruction():
    with patch("packages.ai_providers.gemini_client.genai") as genai_mod:
        with patch("packages.ai_providers.gemini_client.types") as types_mod:
            sdk = MagicMock()
            genai_mod.Client.return_value = sdk
            sdk.models.generate_content.return_value = _mocked_response(
                "hello",
                usage={"prompt_token_count": 11, "candidates_token_count": 22},
            )

            client = GeminiClient(api_key="g-key")
            result = client.complete(
                CompletionRequest(
                    system="you are helpful",
                    messages=[
                        Message(role="user", content="hi"),
                        Message(role="assistant", content="how can I help?"),
                        Message(role="user", content="parse this"),
                    ],
                    temperature=0.3,
                    max_tokens=2048,
                )
            )

            assert result.content == "hello"
            assert result.input_tokens == 11
            assert result.output_tokens == 22

            genai_mod.Client.assert_called_once_with(api_key="g-key")
            kwargs = sdk.models.generate_content.call_args.kwargs
            assert kwargs["model"] == DEFAULT_MODEL
            assert kwargs["contents"] == [
                {"role": "user", "parts": [{"text": "hi"}]},
                {"role": "model", "parts": [{"text": "how can I help?"}]},
                {"role": "user", "parts": [{"text": "parse this"}]},
            ]
            types_mod.GenerateContentConfig.assert_called_once_with(
                system_instruction="you are helpful",
                temperature=0.3,
                max_output_tokens=2048,
            )


def test_complete_uses_request_model_when_provided():
    with patch("packages.ai_providers.gemini_client.genai") as genai_mod:
        with patch("packages.ai_providers.gemini_client.types"):
            sdk = MagicMock()
            genai_mod.Client.return_value = sdk
            sdk.models.generate_content.return_value = _mocked_response("ok")

            client = GeminiClient(api_key="g", model="gemini-2.5-pro")
            client.complete(CompletionRequest(messages=[Message(role="user", content="x")]))

            assert sdk.models.generate_content.call_args.kwargs["model"] == "gemini-2.5-pro"


def test_complete_handles_null_text():
    with patch("packages.ai_providers.gemini_client.genai") as genai_mod:
        with patch("packages.ai_providers.gemini_client.types"):
            sdk = MagicMock()
            genai_mod.Client.return_value = sdk
            response = MagicMock()
            response.text = None
            response.model_dump.return_value = {}
            sdk.models.generate_content.return_value = response

            client = GeminiClient(api_key="g")
            result = client.complete(CompletionRequest(messages=[Message(role="user", content="x")]))
            assert result.content == ""
            assert result.input_tokens == 0
            assert result.output_tokens == 0
