import asyncio
from fastmcp import FastMCP


def test_published_hotel_schema_has_nullable_optionals_and_real_constraints(monkeypatch):
    from hotel_ticket_mcp_server import main
    app = FastMCP("schema-test")
    monkeypatch.setattr(main, "mcp", app)
    main.register_tools()
    tool = asyncio.run(app.get_tool("searchHotels"))
    schema = tool.to_mcp_tool().model_dump(by_alias=True)["inputSchema"]
    assert set(schema["required"]) == {"city", "checkin", "checkout"}
    properties = schema["properties"]
    assert {part["type"] for part in properties["location"]["anyOf"]} == {"string", "null"}
    assert properties["limit"]["minimum"] == 1 and properties["limit"]["maximum"] == 50
    assert properties["limit"]["default"] == 20
    assert properties["children"]["minimum"] == 0
    assert properties["sort"]["enum"] == ["smart", "price_asc", "distance", "score_desc"]
    for name, choices in {
        "room_type": ["大床房", "双床房", "单人床房", "三床房", "特大床房"],
        "accommodation_type": ["酒店", "民宿", "青年旅馆", "酒店公寓", "公寓"],
    }.items():
        assert properties[name]["anyOf"] == [{"enum": choices, "type": "string"}, {"type": "null"}]
        assert properties[name]["default"] is None
    assert "暂不支持" in properties["breakfast"]["description"]
    assert "get_tool_details" in tool.description
