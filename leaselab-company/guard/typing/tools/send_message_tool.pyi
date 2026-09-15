"""Native send_message adapter, called only after the guard validates its JSON."""
JSONValue = str | int | float | bool | None | list['JSONValue'] | dict[str, 'JSONValue']

def send_message_tool(args: JSONValue, **kwargs: JSONValue) -> str: ...
