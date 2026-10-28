"""Build/verify the local project-learning artifact without importing Wenxi."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def js_json(value: object) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def steps_in(value):
    if isinstance(value, dict):
        if "layer" in value and "filePath" in value:
            yield value
        for child in value.values():
            yield from steps_in(child)
    elif isinstance(value, list):
        for child in value:
            yield from steps_in(child)


def validate(doc):
    from jsonschema import Draft202012Validator, FormatChecker

    schema = json.loads(
        (HERE / "project-learning-schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(doc)
    sections = [s for ch in doc["chapters"] for s in ch["sections"]]
    anchors = [s["anchor"] for s in sections]
    assert len(anchors) == len(set(anchors)), "Duplicate section anchors"
    assert all(re.fullmatch("[a-z][a-z0-9-]*", x) for x in anchors)
    assert all(s["blocks"][0]["type"] == "text" for s in sections), (
        "Concept text must come first"
    )
    groups = Counter(
        s.get("groupTitle")
        for ch in doc["chapters"]
        if ch["id"] == "practice"
        for s in ch["sections"]
    )
    assert len(groups) == 6 and all(4 <= n <= 8 for n in groups.values()), groups
    steps = list(steps_in(doc))
    for item in steps:
        match = re.fullmatch(r"(.+):(\d+)-(\d+)", item["filePath"])
        assert match, item["filePath"]
        rel, lo, hi = match.group(1), int(match.group(2)), int(match.group(3))
        path = (ROOT / rel).resolve()
        assert path.is_relative_to(ROOT) and path.is_file(), rel
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        assert 1 <= lo <= hi <= len(lines), item["filePath"]
        assert 5 <= hi - lo + 1 <= 15, f"Standard snippet length: {item['filePath']}"
        assert item.get("code") == "\n".join(lines[lo - 1 : hi]), (
            f"Stale snippet: {item['filePath']}"
        )
        assert len(re.findall(r"[。！？]", item["explanation"])) >= 2, item["filePath"]
    assert sum(bool(x.get("keyPoint")) for x in steps) >= len(steps) * 0.5
    return sections, steps, groups


def collect_sources(doc, steps):
    paths = {re.sub(r":\d+-\d+$", "", s["filePath"]) for s in steps}
    raw = json.dumps(doc, ensure_ascii=False)
    paths.update(
        re.findall(
            r"(?:backend|frontend/src|tests|scripts|contracts|evals/rag|docs/adr|docs/runbooks|migrations)/[A-Za-z0-9_./-]+\.(?:py|ts|vue|json|md|yml|sh|ps1)",
            raw,
        )
    )
    paths.update(
        [
            "README.md",
            "CONTEXT.md",
            "pyproject.toml",
            "frontend/package.json",
            "frontend/vite.config.ts",
            "backend/api/router.py",
            "backend/launcher.py",
        ]
    )
    paths.update(re.findall(r"\]\(\.\./\.\./\.\./([^\s)#]+)", raw))
    sources = {}
    for rel in sorted(paths):
        path = (ROOT / rel).resolve()
        assert path.is_relative_to(ROOT) and path.is_file(), (
            f"Missing cited source: {rel}"
        )
        assert path.suffix in {
            ".py",
            ".ts",
            ".mjs",
            ".vue",
            ".json",
            ".md",
            ".yml",
            ".toml",
            ".sh",
            ".ps1",
        }, rel
        assert not any(x.startswith(".") for x in Path(rel).parts), rel
        content = path.read_text(encoding="utf-8-sig")
        sources[rel] = {"content": content, "sha256": digest(path.read_bytes())}
    return sources


def build_html(doc):
    page = (HERE / "vendor/template.html").read_text(encoding="utf-8-sig")
    page = re.sub(
        r'<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js" crossorigin="anonymous"></script>',
        '<script src="./vendor/highlight.min.js"></script>',
        page,
    )
    page = re.sub(
        r'<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.2/marked.min.js" crossorigin="anonymous"></script>',
        '<script src="./vendor/marked.min.js"></script>\n<script src="./vendor/purify.min.js"></script>',
        page,
    )
    page = re.sub(
        r'<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js" crossorigin="anonymous"></script>',
        '<script src="./vendor/mermaid.min.js"></script>',
        page,
    )
    page = page.replace(
        "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css",
        "./vendor/github-dark.min.css",
    )
    page = page.replace(
        "const EMBEDDED_DATA = null;", "const EMBEDDED_DATA = " + js_json(doc) + ";"
    )
    old = "  try { const r = await fetch('./project-learning.json'); docData = r.ok ? await r.json() : null; }\n  catch (e) { docData = null; }"
    assert old in page
    page = page.replace(old, "  docData = EMBEDDED_DATA;")
    page = page.replace(
        "localStorage.getItem('pl-theme')",
        "safeStorage.getItem('wenxi-learning-theme')",
    )
    page = page.replace("localStorage.", "safeStorage.")
    page = page.replace("'pl-", "'wenxi-learning-")
    page = page.replace(
        "let docData = null",
        """const safeStorage = {
  getItem(key) { try { return localStorage.getItem(key); } catch { return null; } },
  setItem(key, value) { try { localStorage.setItem(key, value); } catch {} }
};
function renderMarkdown(value) {
  const html = DOMPurify.sanitize(marked.parse(value));
  const root = document.createElement('div'); root.innerHTML = html;
  root.querySelectorAll('a').forEach(a => {
    const href = a.getAttribute('href') || '';
    if (href.startsWith('../../../')) {
      const parts = href.slice(9).split('#');
      a.href = './source.html?file=' + encodeURIComponent(parts[0]) + (parts[1] ? '#'+parts[1] : '');
      a.target = '_blank'; a.rel = 'noopener';
    } else if (/^https?:/.test(href)) { a.target = '_blank'; a.rel = 'noopener noreferrer'; }
  });
  return root.innerHTML;
}
if (typeof mermaid !== 'undefined') mermaid.initialize({startOnLoad:false,securityLevel:'strict',theme:'default'});
let docData = null""",
    )
    page = (
        page.replace("marked.parse(b.text||'')", "renderMarkdown(b.text||'')")
        .replace("marked.parse(ep.description)", "renderMarkdown(ep.description)")
        .replace("marked.parse(q.answer||'')", "renderMarkdown(q.answer||'')")
    )
    page = re.sub(r"^\s*console\.log\([^\n]+\);", "", page, flags=re.M)
    page = page.replace(
        "const url = location.origin + location.pathname + '#' + anchor;",
        "const target = new URL(location.href); target.hash = anchor; const url = target.href;",
    )
    # Paths open a frozen source viewer, rather than a server exposing the repository.
    page = page.replace("esc(s.filePath||'')", "sourceLink(s.filePath||'')")
    page = page.replace(
        "function renderCallchainStep(s) {",
        """function sourceLink(ref) {
  const match = ref.match(/^(.+):(\\d+)-(\\d+)$/);
  if (!match) return esc(ref);
  return '<a href="./source.html?file='+encodeURIComponent(match[1])+'#L'+match[2]+'" target="_blank" rel="noopener">'+esc(ref)+'</a>';
}
function renderCallchainStep(s) {""",
    )
    page = page.replace(
        "<pre><code>'+clines",
        "<pre><code class=\"language-'+esc(s.language||'python')+'\">'+clines",
    )
    page = page.replace(
        "if (typeof hljs !== 'undefined') hljs.highlightElement(el);",
        "if (typeof hljs !== 'undefined' && !el.dataset.highlighted) hljs.highlightElement(el);",
    )
    page = page.replace(
        "if (typeof hljs!=='undefined') hljs.highlightElement(el);",
        "if (typeof hljs!=='undefined' && !el.dataset.highlighted) hljs.highlightElement(el);",
    )
    page = page.replace(
        "if(typeof hljs!=='undefined')hljs.highlightElement(el);",
        "if(typeof hljs!=='undefined' && !el.dataset.highlighted)hljs.highlightElement(el);",
    )
    page = page.replace(
        "el.innerHTML = el.getAttribute('data-original') || el.textContent || '';",
        "el.textContent = el.getAttribute('data-original') || el.textContent || '';",
    )
    page = page.replace(
        "if (typeof marked!=='undefined')",
        "document.addEventListener('keydown', e => { if ((e.key==='Enter'||e.key===' ') && e.target.matches('.question-header')) {e.preventDefault();e.target.click();} });\nif (typeof marked!=='undefined')",
    )
    page = page.replace(
        'class="question-header" onclick=',
        'class="question-header" role="button" tabindex="0" onclick=',
    )
    page = page.replace(
        "    showSection(initialIdx, true);",
        "    document.querySelectorAll('.toc-chapter').forEach((el,i)=>{if(i>1){el.classList.add('collapsed');el.querySelector('.toc-chapter-header').setAttribute('aria-expanded','false');}});\n    showSection(initialIdx, true);",
    )
    page = page.replace(
        "  const sec = allSections[idx];",
        "  updateStudyProgress();\n  const sec = allSections[idx];",
    )
    page = page.replace(
        "function navigateSection(dir) {",
        """function updateStudyProgress() {
  let viewed=[]; try { viewed=JSON.parse(safeStorage.getItem('wenxi-learning-viewed')||'[]'); } catch {}
  const valid=new Set(allSections.map(s=>s.anchor));
  const n=new Set(viewed.filter(a=>valid.has(a))).size;
  document.getElementById('studyProgress').textContent='已读 '+n+' / '+allSections.length;
}
function navigateSection(dir) {""",
    )
    page = page.replace(
        '<button class="theme-toggle" id="themeToggle"',
        '<span id="studyProgress" class="study-progress" aria-live="polite"></span><button class="theme-toggle" id="themeToggle"',
    )
    page = page.replace(
        'placeholder="搜索文档..."',
        'placeholder="搜索概念、文件或问题..." aria-label="搜索学习文档"',
    )
    page = page.replace(
        "      sec.blocks.forEach(b =>",
        "      secHtml += '<div class=\"study-meta\">'+(sec.estimatedMinutes?'建议 '+sec.estimatedMinutes+' 分钟 · ':'')+({beginner:'入门',intermediate:'进阶',advanced:'深入'}[sec.difficulty]||'')+'</div>';\n      sec.blocks.forEach(b =>",
    )
    page = page.replace(
        "  document.title = meta.projectName",
        "  document.documentElement.dataset.snapshot = meta.generatedAt;\n  document.title = meta.projectName",
    )
    page = page.replace(
        "</style>",
        """
:root {--accent-primary:#247c70;--accent-secondary:#37665f;--accent-green:#53876c;--grad-terracotta:linear-gradient(140deg,#247c70,#58a58b);--grad-blue:linear-gradient(140deg,#37665f,#6b9785);}
[data-theme="dark"] {--bg-root:#102320;--bg-root-gradient:linear-gradient(175deg,#102320,#152d27);--bg-surface:#19302a;--bg-subtle:#203c33;--bg-glass:rgba(25,48,42,.9);--text-primary:#e3eee6;--text-secondary:#b9cfc0;--text-tertiary:#8ca99a;--border-card:#375449;--border-glass:#375449;--accent-primary:#84c5ae;--accent-secondary:#a6c7bd;}
.text-content {line-height:1.95;} .text-content p {margin-bottom:1em;}
.callchain-step-file a {color:inherit;text-underline-offset:3px;overflow-wrap:anywhere;}
.study-meta {font-size:.78rem;color:var(--text-tertiary);margin:-10px 0 25px;}
.study-progress {font-size:.72rem;color:var(--text-secondary);white-space:nowrap;}
.code-block-body pre {tab-size:4;} .text-content pre {white-space:pre-wrap;overflow-wrap:anywhere;}
.mermaid {min-width:0;overflow:auto;} .mermaid svg {max-width:100%;height:auto;}
.question-header:focus-visible,button:focus-visible,a:focus-visible {outline:2px solid var(--accent-primary);outline-offset:3px;}
@media(max-width:600px){.study-progress{display:none;}.topbar-title{font-size:.85rem;}.topbar-search{max-width:45%;}.section-nav{padding:10px;}.section-nav-btn{padding:8px;font-size:.72rem;}.section-heading{font-size:1.55rem;}}
@media print {html,body,.layout,.main-content{height:auto!important;overflow:visible!important;} .section-viewport{height:auto!important;overflow:visible!important;} .study-meta{margin:0 0 15px;}}
</style>""",
    )
    page = (
        "<!-- Generated by build.py from project-learning.json and the attributed upstream template. -->\n"
        + page
    )
    return page


def source_viewer():
    return """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Wenxi · 源码快照</title>
<style>*{box-sizing:border-box}body{margin:0;background:#faf7f2;color:#20382f;font:14px system-ui,"Microsoft YaHei",sans-serif}header{padding:24px;position:sticky;top:0;background:#faf7f2;border-bottom:1px solid #d9dfd6;z-index:1}h1{font-size:18px;margin:12px 0;overflow-wrap:anywhere}small{color:#567565;overflow-wrap:anywhere}a{color:#247c70}.source{padding:16px 0;overflow:auto}.line{display:flex;min-width:max-content;line-height:1.75;font:13px/1.75 Consolas,"Cascadia Code",monospace;scroll-margin-top:160px}.line:target{background:#d4e9d9}.number{display:inline-block;width:70px;flex-shrink:0;text-align:right;padding-right:20px;color:#81978a;user-select:none}.code{white-space:pre;padding-right:30px;tab-size:4}</style>
<header><a href="./index.html">← 返回学习文档</a><h1 id="title">源码快照</h1><small id="hash"></small><p>这是生成学习材料时的只读快照。当前仓库可能已变化；用 build.py --check 校验。</p></header><main id="source" class="source"></main><script src="./source-data.js"></script><script>
const file=new URLSearchParams(location.search).get('file');const entry=WENXI_SOURCES[file];
if(!entry){document.getElementById('source').textContent='该文件未包含在本次引用快照中。';}
else{document.title=file+' · Wenxi 源码';document.getElementById('title').textContent=file;document.getElementById('hash').textContent='SHA-256 '+entry.sha256;const fragment=document.createDocumentFragment();entry.content.split('\\n').forEach((text,i)=>{const row=document.createElement('div');row.className='line';row.id='L'+(i+1);const a=document.createElement('a');a.className='number';a.href='#'+row.id;a.textContent=i+1;const code=document.createElement('span');code.className='code';code.textContent=text||' ';row.append(a,code);fragment.append(row);});document.getElementById('source').append(fragment);requestAnimationFrame(()=>{const target=document.getElementById(location.hash.slice(1));if(target)target.scrollIntoView();});}
</script></html>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Read-only validation; fail on stale source or generated files",
    )
    args = parser.parse_args()
    doc = json.loads((HERE / "project-learning.json").read_text(encoding="utf-8"))
    sections, steps, groups = validate(doc)
    sources = collect_sources(doc, steps)
    output = {
        "index.html": build_html(doc),
        "source.html": source_viewer(),
        "source-data.js": "const WENXI_SOURCES = " + js_json(sources) + ";\n",
    }
    for filename, content in output.items():
        path = HERE / filename
        if args.check:
            assert path.read_text(encoding="utf-8") == content, (
                f"Rebuild required: {filename}"
            )
        else:
            path.write_text(content, encoding="utf-8")
    referenced = {
        p: {"sha256": s["sha256"], "lines": len(s["content"].splitlines())}
        for p, s in sources.items()
    }
    if args.check:
        manifest = json.loads(
            (HERE / "source-manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["sources"] == referenced, "Source manifest changed"
        for name, sha in manifest["assets"].items():
            assert digest((HERE / name).read_bytes()) == sha, name
    else:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        manifest = {
            "generatedAt": doc["meta"]["generatedAt"],
            "gitHead": head,
            "workingTree": "includes uncommitted changes; source hashes are authoritative for this learning snapshot",
            "skill": "https://github.com/xWebt/project-learning-skill",
            "sources": referenced,
            "assets": {
                p.relative_to(HERE).as_posix(): digest(p.read_bytes())
                for p in sorted((HERE / "vendor").iterdir())
                if p.is_file()
            },
        }
        (HERE / "source-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    report = {
        "mode": "check" if args.check else "build",
        "chapters": len(doc["chapters"]),
        "sections": len(sections),
        "modules": dict(groups),
        "callchainSteps": len(steps),
        "sourceFiles": len(sources),
        "interviewQuestions": sum(
            b["type"] == "question" for s in sections for b in s["blocks"]
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
