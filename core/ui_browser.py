"""core/ui_browser.py — a real tree for the one place the desktop tree is empty.

WHY THIS EXISTS
    A browser window publishes almost nothing useful to UI Automation: one big
    document node, and then whatever the browser's own chrome offers. Every page
    rendered inside it — every button, field, menu and table — is invisible to
    the accessibility tree unless the page was written to expose it.

    That is the weakness worth naming plainly: a tree-based approach is only as
    good as the tree. For a browser it is also unnecessary, because the page
    *already* has a perfect tree — the DOM — and Playwright can read it.

    So the ladder is not "tree or vision". For web content it is DOM, which is
    structure, refs and staleness exactly like UI Automation, and which works on
    pages that never emitted an accessibility node in their lives.

WHY REFS ARE WRITTEN INTO THE PAGE
    Playwright's accessibility snapshot gives roles and names but no stable
    handle to act on. This adapter annotates each element with a
    `data-ultron-ref` attribute during the snapshot and addresses it afterwards
    by that attribute. Every element is annotated, including containers the
    renderer will not print, because the numbering has to be the same in the page
    and in the snapshot or a ref would point at two different things. Two
    consequences, both deliberate:

      - The ref in the page and the ref in the snapshot are the same string, so
        a stale one is detectable before the click.
      - Annotation is removable (`clear_refs`) and never touches anything the
        page reads: one extra data attribute, no event handlers, no globals.

WHAT IS VERIFIED
    The tree builder, the ref discipline and the fallback (`tests/test_ui_ladder.py`)
    are verified with a fake page. The Playwright calls are written against its
    sync API and are unverified here, because no browser runs in this
    environment. Do not claim web control works until it has been run.
"""

from __future__ import annotations
from core import failures

from typing import Any

from core.ui_tree import Node

# The role vocabulary a page can claim. Anything else is mapped to its tag name,
# which is enough for `ui_tree` to normalise or ignore.
INTERACTIVE_ROLES = frozenset(
    {
        "button", "link", "textbox", "searchbox", "combobox", "checkbox", "radio",
        "tab", "menuitem", "option", "switch", "slider", "spinbutton", "listitem",
        "treeitem", "gridcell", "row",
    }
)

# One pass over the DOM, top-down, producing the same shape the Windows adapter
# produces. Written as a string because that is what Playwright evaluates; it is
# deliberately dependency-free and does not touch the page's own objects.
SNAPSHOT_JS = r"""
(snapshotId, maxDepth, maxNodes) => {
  let counter = 0;
  let redacted = 0;
  const roleOf = (el) => {
    const explicit = (el.getAttribute('role') || '').trim().toLowerCase();
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    const map = {
      a: 'link', button: 'button', input: 'textbox', textarea: 'textbox',
      select: 'combobox', option: 'option', img: 'image', h1: 'text', h2: 'text',
      h3: 'text', p: 'text', li: 'listitem', ul: 'list', ol: 'list',
      table: 'table', tr: 'row', td: 'cell', th: 'cell', form: 'group',
      nav: 'navigation', header: 'banner', footer: 'contentinfo', label: 'text',
      dialog: 'dialog', section: 'region', article: 'article', span: 'text',
      div: 'group', main: 'main', aside: 'complementary'
    };
    if (tag === 'input') {
      const type = (el.getAttribute('type') || 'text').toLowerCase();
      if (type === 'checkbox') return 'checkbox';
      if (type === 'radio') return 'radio';
      if (type === 'submit' || type === 'button' || type === 'reset') return 'button';
      if (type === 'password') return 'password';
      if (type === 'search') return 'searchbox';
      if (type === 'range') return 'slider';
      if (type === 'number') return 'spinbutton';
    }
    return map[tag] || tag;
  };
  const nameOf = (el) => {
    const aria = el.getAttribute('aria-label');
    if (aria) return aria.trim();
    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy && el.ownerDocument) {
      const target = el.ownerDocument.getElementById(labelledBy);
      if (target && target.textContent) return target.textContent.trim().slice(0, 120);
    }
    if (el.tagName.toLowerCase() === 'input') {
      const type = (el.getAttribute('type') || 'text').toLowerCase();
      if (type === 'submit' || type === 'button' || type === 'reset') {
        return (el.value || '').trim();
      }
      const id = el.getAttribute('id');
      if (id && el.ownerDocument) {
        const label = el.ownerDocument.querySelector(`label[for="${id}"]`);
        if (label && label.textContent) return label.textContent.trim().slice(0, 120);
      }
    }
    const text = (el.innerText || el.textContent || '').trim();
    if (text) return text.replace(/\s+/g, ' ').slice(0, 120);
    return (el.getAttribute('placeholder') || el.getAttribute('title') || '').trim();
  };
  const actionsOf = (el, role) => {
    const actions = [];
    if (['button', 'link', 'menuitem', 'tab', 'option', 'checkbox', 'radio',
         'switch', 'treeitem', 'row', 'gridcell'].includes(role)) actions.push('click');
    if (['textbox', 'searchbox', 'spinbutton', 'combobox', 'slider'].includes(role)) {
      actions.push('set_value');
    }
    if (role === 'checkbox' || role === 'switch') actions.push('toggle');
    if (el.tagName.toLowerCase() === 'select') actions.push('set_value');
    actions.push('focus');
    return Array.from(new Set(actions));
  };
  const walk = (el, depth) => {
    if (counter >= maxNodes) return null;
    counter += 1;
    const role = roleOf(el);
    const name = nameOf(el);
    const isSecret = role === 'password';
    let value = '';
    if (!isSecret) {
      if (el.tagName.toLowerCase() === 'select') value = el.value || '';
      else if ('value' in el && typeof el.value === 'string') value = el.value;
      else value = '';
    } else {
      redacted += 1;
    }
    const refId = '@' + snapshotId + ':e' + (counter - 1);
    el.setAttribute('data-ultron-ref', refId);
    const style = window.getComputedStyle(el);
    const visible = style.display !== 'none' && style.visibility !== 'hidden'
      && el.getClientRects().length > 0;
    const enabled = !el.disabled && el.getAttribute('aria-disabled') !== 'true';
    const children = [];
    if (depth > 0) {
      for (const child of Array.from(el.children)) {
        const node = walk(child, depth - 1);
        if (node) children.push(node);
      }
    }
    const actionable = actionsOf(el, role);
    return {
      role, name, value, ref: refId,
      node_id: refId,
      enabled, visible,
      actions: actionable,
      sensitive: isSecret,
      children_total: el.children.length,
      children,
    };
  };
  const body = document.body;
  if (!body) return { tree: null, redacted: 0, nodes: 0 };
  const tree = walk(document.documentElement, maxDepth);
  return { tree, redacted, nodes: counter };
}
"""

CLEAR_JS = r"""
() => {
  document.querySelectorAll('[data-ultron-ref]').forEach(
    (el) => el.removeAttribute('data-ultron-ref')
  );
  return document.querySelectorAll('[data-ultron-ref]').length;
}
"""


def _node_from_dict(payload: dict) -> Node:
    children = tuple(_node_from_dict(child) for child in payload.get("children") or ())
    return Node(
        role=str(payload.get("role") or ""),
        name=str(payload.get("name") or ""),
        value="" if payload.get("sensitive") else str(payload.get("value") or ""),
        node_id=str(payload.get("node_id") or ""),
        enabled=bool(payload.get("enabled", True)),
        visible=bool(payload.get("visible", True)),
        actions=tuple(str(a) for a in payload.get("actions") or ()),
        children=children,
        sensitive=bool(payload.get("sensitive")),
    )


class BrowserAdapter:
    """Playwright page as an `core.ui_action.Adapter`.

    The page is injected rather than launched, because the assistant already owns
    a browser through `actions/browser_control.py` and two owners of one profile
    is how a 'Who's using Chrome?' picker appears on screen.
    """

    name = "browser"

    def __init__(self, page: Any, max_depth: int = 8, max_nodes: int = 400) -> None:
        self.page = page
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.snapshot_id = ""

    def capabilities(self) -> set[str]:
        if self.page is None:
            return set()
        return {"dom", "headless", "keyboard"}

    # ------------------------------------------------------------------ snapshot
    def snapshot(self, app: str = "", root_ref: str | None = None,
                 max_depth: int | None = None) -> Node:
        from core.ui_action import ui_error

        if self.page is None:
            raise ui_error("NO_ADAPTER", "no browser page is attached")
        depth = self.max_depth if max_depth is None else max_depth
        try:
            payload = self.page.evaluate(
                SNAPSHOT_JS, [self.snapshot_id or "browser", depth, self.max_nodes]
            )
        except Exception as exc:
            raise ui_error("ADAPTER_FAILED", f"page evaluation failed: {exc}") from exc
        tree = (payload or {}).get("tree")
        if not tree:
            raise ui_error("NO_TREE", "the page returned no document body")
        node = _node_from_dict(tree)
        if root_ref:
            # Drill-down: keep the same DOM but prune to the requested subtree.
            node = _prune_to(node, root_ref) or node
        return node

    def set_snapshot_id(self, snapshot_id: str) -> None:
        """Called by the session so page refs and snapshot refs agree."""
        self.snapshot_id = snapshot_id

    # -------------------------------------------------------------------- action
    def perform(self, entry, action: str, value: str = "") -> None:
        from core.ui_action import ui_error

        ref = getattr(entry, "ref", "")
        if not ref:
            raise ui_error("INVALID_ARGS", "no ref to act on")
        selector = f'[data-ultron-ref="{ref}"]'
        verb = str(action or "").strip().lower()
        try:
            locator = self.page.locator(selector).first
            if verb in ("click", "invoke", "press", "select", "toggle", "expand"):
                locator.click(timeout=5000)
                return
            if verb in ("type", "set_value"):
                if getattr(entry, "role", "") in ("combo_box", "list_item", "option"):
                    locator.select_option(label=str(value))
                else:
                    locator.fill(str(value), timeout=5000)
                return
            if verb == "focus":
                locator.focus(timeout=5000)
                return
            if verb == "scroll":
                locator.scroll_into_view_if_needed(timeout=5000)
                return
            raise ui_error("UNSUPPORTED_ACTION", f"'{verb}' is not available in a page")
        except Exception as exc:
            if getattr(exc, "code", None):
                raise
            message = str(exc)
            code = "STALE_REF" if "not attached" in message or "detached" in message else "ADAPTER_FAILED"
            raise ui_error(code, f"page action failed: {message}") from exc

    def probe(self, entry) -> tuple[bool, bool] | None:
        ref = getattr(entry, "ref", "")
        if not ref:
            return None
        try:
            state = self.page.evaluate(
                """
                (ref) => {
                  const el = document.querySelector(`[data-ultron-ref="${ref}"]`);
                  if (!el) return null;
                  const style = window.getComputedStyle(el);
                  return {
                    visible: style.display !== 'none' && style.visibility !== 'hidden'
                             && el.getClientRects().length > 0,
                    enabled: !el.disabled && el.getAttribute('aria-disabled') !== 'true'
                  };
                }
                """,
                ref,
            )
        except Exception:  # noqa: BLE001
            return None
        if not state:
            return None
        return (bool(state.get("visible")), bool(state.get("enabled")))

    def clear_refs(self) -> None:
        try:
            self.page.evaluate(CLEAR_JS)
        except Exception as error:  # noqa: BLE001, S110
            failures.note("ui_browser.clear_refs", error)


def _prune_to(node: Node, ref: str) -> Node | None:
    """The subtree whose ref matches, re-rooted, or None."""
    if node.node_id == ref:
        return node
    for child in node.children:
        found = _prune_to(child, ref)
        if found is not None:
            return found
    return None
