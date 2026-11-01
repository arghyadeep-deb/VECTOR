"""SDK streaming adapters: emit text only and retain complete tool proposals for approval."""


def openai_response(client, kwargs, on_delta):
    params = dict(kwargs)
    params.pop("stream", None)
    params["stream_options"] = dict(params.get("stream_options") or {}, include_usage=True)
    with client.chat.completions.stream(**params) as stream:
        for event in stream:
            if event.type == "content.delta":
                on_delta(event.delta)
        return stream.get_final_completion()


def anthropic_response(client, kwargs, on_delta):
    params = dict(kwargs)
    params.pop("stream", None)
    with client.messages.stream(**params) as stream:
        for text in stream.text_stream:
            on_delta(text)
        return stream.get_final_message()


def ollama_response(client, kwargs, on_delta):
    params = dict(kwargs, stream=True)
    content, calls, final = [], [], {}
    for chunk in client.chat(**params):
        data = chunk if isinstance(chunk, dict) else chunk.model_dump()
        final = data
        message = data.get("message") or {}
        text = message.get("content") or ""
        if text:
            content.append(text)
            on_delta(text)
        calls.extend(message.get("tool_calls") or [])
    return dict(final, message={"content": "".join(content), "tool_calls": calls})


if __name__ == "__main__":
    assert callable(openai_response) and callable(ollama_response)
