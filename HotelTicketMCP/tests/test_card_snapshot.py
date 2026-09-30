"""Execute both production JavaScript extractors against hotel-card DOM doubles."""
import ast
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from hotel_ticket_mcp_server.tools.hotel_search_tools import SNAPSHOT_JS


HARNESS = """
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
// The scoped room selector and review text come from the captured Ctrip card.
const children = input.cards.map(card => ({
  innerText: card.text,
  querySelectorAll: () => [],
  querySelector: selector => selector === '.room-info .room-name' && card.roomNode !== null
    ? {innerText: card.roomNode} : null,
}));
const document = {querySelector: selector => selector === '.hotel-list' ? {children} : null};
const execute = input.kind === 'snapshot'
  ? new Function('document', input.script)
  : new Function('document', `return (${input.script})();`);
Promise.resolve(execute(document)).then(result => {
  process.stdout.write(JSON.stringify(result.map(card => card.room)));
}).catch(error => { console.error(error); process.exitCode = 1; });
"""


def legacy_extractor():
    path = Path(__file__).resolve().parents[2] / "scripts/scrape_ctrip_hotels_edge.py"
    # Read the literal without importing Playwright or starting a browser.
    for statement in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "EXTRACT_JS"
            for target in statement.targets
        ):
            return ast.literal_eval(statement.value)
    raise AssertionError("Legacy extractor was not found")


@pytest.mark.parametrize("kind", ["snapshot", "legacy"])
def test_room_comes_from_room_node_instead_of_card_keywords(kind):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is needed to execute browser snapshot JavaScript")
    long_room = "豪华大床房（" + "落地窗、投影、早餐、" * 8 + "）"
    samples = [
        # Actual failing hotel card: its review occurs before the room name.
        ("维也纳国际酒店(武汉杨泗港长江大桥店)", '"服务热情周到，早餐健康，房间很大"', "标准大床房"),
        # A hotel name containing 房/床 must never become the room type.
        ("舒适大床房酒店", '"床很舒服"', "商务套间"),
        ("长房型名称酒店", '"房间宽敞"', long_room),
        # No dedicated room node: report unknown instead of guessing from reviews.
        ("房型未展示酒店", '"房间很大，床很舒服"', None),
        ("空房型节点酒店", '"房间干净"', "   "),
    ]
    cards = [{
        "text": "\n".join([name, "4.7", "1,617条点评", review, room or "",
                            "热卖！低价房仅剩4间", "¥196", "查看详情"]),
        "roomNode": room,
    } for name, review, room in samples]
    # Twenty cards let the legacy extractor finish without its unrelated scrolling.
    payload = {"kind": kind, "script": SNAPSHOT_JS if kind == "snapshot" else legacy_extractor(),
               "cards": cards * 4}
    completed = subprocess.run(
        [node, "-e", HARNESS], input=json.dumps(payload, ensure_ascii=False),
        capture_output=True, text=True, encoding="utf-8", check=True, timeout=10,
    )
    assert json.loads(completed.stdout) == [(room or "").strip() for _, _, room in samples] * 4
