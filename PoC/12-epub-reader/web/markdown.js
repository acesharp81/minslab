/* Standalone UTF-8 Markdown books. Parsing and storage stay in the browser. */
import { Marked } from './vendor/marked.js';
const markdown = new Marked({ gfm: true, breaks: false, async: false });
const headingSelector = 'h1,h2,h3,h4,h5,h6';

export class MarkdownBook {
  static async load(buffer, filename = '책.md') {
    if (buffer.byteLength > 5 * 1024 * 1024) throw new Error('Markdown 파일은 5 MB 이하로 선택해 주세요.');
    let source;
    try { source = new TextDecoder('utf-8', { fatal: true }).decode(buffer); }
    catch { throw new Error('Markdown 파일을 UTF-8 인코딩으로 저장한 뒤 다시 추가해 주세요.'); }
    if (!source.trim() || /\u0000/.test(source)) throw new Error('본문이 있는 UTF-8 Markdown 파일을 선택해 주세요.');
    source = source.replace(/\r\n?/g, '\n');
    const metadata = {};
    // Read only scalar title/author fields; never evaluate YAML or custom HTML.
    const frontmatter = source.match(/^---\n([\s\S]*?)\n---(?:\n|$)/);
    if (frontmatter && /^(?:title|author):/m.test(frontmatter[1])) {
      for (const line of frontmatter[1].split('\n')) {
        const field = line.match(/^(title|author):\s*(.*?)\s*$/);
        if (field) metadata[field[1]] = field[2].replace(/^(['"])(.*)\1$/, '$2');
      }
      source = source.slice(frontmatter[0].length);
    }
    const body = DOMPurify.sanitize(markdown.parse(source), {
      RETURN_DOM: true,
      ALLOWED_TAGS: ['p','br','hr','h1','h2','h3','h4','h5','h6','strong','b','em','i','del','s','ul','ol','li','blockquote','pre','code','table','thead','tbody','tfoot','tr','th','td','a','img','input','sup','sub','kbd','details','summary','div','span'],
      ALLOWED_ATTR: ['href','id','title','alt','colspan','rowspan','start','align','type','checked'],
      ALLOW_DATA_ATTR: false, ALLOW_ARIA_ATTR: false,
      FORBID_CONTENTS: ['script','style','iframe','object','template','svg','math'],
    });
    for (const input of body.querySelectorAll('input')) {
      if (input.type !== 'checkbox') { input.remove(); continue; }
      const check = document.createElement('span'); check.className = 'md-check';
      check.textContent = input.hasAttribute('checked') ? '☑ ' : '☐ ';
      check.setAttribute('aria-label', input.hasAttribute('checked') ? '완료' : '미완료'); input.replaceWith(check);
    }
    for (const img of body.querySelectorAll('img')) {
      const placeholder = document.createElement('span'); placeholder.className = 'md-image';
      placeholder.textContent = `이미지 · ${img.getAttribute('alt') || '설명 없음'}`;
      placeholder.title = 'Markdown의 별도 이미지 파일은 포함되지 않습니다.'; img.replaceWith(placeholder);
    }
    // Disclosure widgets cannot hide text from pagination or persisted anchors.
    for (const node of body.querySelectorAll('details,summary')) {
      const replacement = document.createElement(node.tagName === 'SUMMARY' ? 'strong' : 'div');
      replacement.append(...node.childNodes); node.replaceWith(replacement);
    }
    for (const cell of body.querySelectorAll('[align]')) {
      const align = cell.getAttribute('align'); cell.removeAttribute('align');
      if (['left','center','right'].includes(align)) cell.className = `md-align-${align}`;
    }
    if (!body.textContent.trim()) throw new Error('읽을 수 있는 Markdown 본문이 없습니다.');
    const book = new MarkdownBook();
    book.title = metadata.title || body.querySelector('h1')?.textContent.trim() || filename.replace(/\.(md|markdown)$/i, '');
    book.author = metadata.author || '저자 미상'; book.cover = null; book.spine = []; book.toc = []; book.sections = [];
    for (const node of body.querySelectorAll('[id]')) node.removeAttribute('id');
    const ids = new Set();
    for (const heading of body.querySelectorAll(headingSelector)) {
      const base = heading.textContent.trim().normalize('NFC').toLowerCase().replace(/[^\p{L}\p{N}\p{M}_\s-]/gu, '').replace(/\s+/g, '-') || 'section';
      let id = base, suffix = 1; while (ids.has(id)) id = `${base}-${suffix++}`;
      ids.add(id); heading.id = id;
    }
    let section = document.createElement('div');
    const flush = () => { if (section.textContent.trim()) book.sections.push(section); section = document.createElement('div'); };
    for (const node of [...body.childNodes]) {
      if (node.nodeType === 1 && node.matches('h1,h2')) flush();
      section.append(node);
    }
    flush();
    const targets = new Map();
    book.sections.forEach((section, index) => {
      const path = `markdown/section-${index}`, headings = [...section.querySelectorAll(headingSelector)];
      const label = headings[0]?.textContent.trim() || (index === 0 ? book.title : `${index + 1}장`);
      book.spine.push({ path, label });
      for (const heading of headings) {
        targets.set(heading.id, path);
        book.toc.push({ path, hash: heading.id, label: heading.textContent.trim(), depth: Number(heading.tagName[1]) - 1 });
      }
      if (!headings.length) book.toc.push({ path, hash: '', label, depth: 0 });
      section.querySelectorAll('p,h1,h2,h3,h4,h5,h6,li,blockquote,pre,table,hr').forEach((node, block) => { node.dataset.readerBlock = String(block); });
    });
    book.sections = book.sections.map(section => {
      for (const link of section.querySelectorAll('a')) {
        const href = link.getAttribute('href') || ''; link.removeAttribute('href');
        let hash; try { if (href.startsWith('#')) hash = decodeURIComponent(href.slice(1)); } catch { /* malformed anchor remains text */ }
        if (hash && targets.has(hash)) {
          link.setAttribute('href', `#${hash}`); link.dataset.bookPath = targets.get(hash); link.dataset.bookHash = hash;
        } else { link.className = 'md-reference'; if (/^https?:\/\//i.test(href)) link.title = href; }
      }
      return section.innerHTML;
    });
    return book;
  }
  async chapter(index) { return this.sections[index]; }
  destroy() { this.sections = []; }
}

export const readerStyles = `
#reader-flow h1,#reader-flow h2,#reader-flow h3,#reader-flow h4,#reader-flow h5,#reader-flow h6{font-family:system-ui,sans-serif;font-weight:700;letter-spacing:-.025em;break-after:avoid}
h1{font-size:1.85em;line-height:1.3;margin-bottom:.9em}h2{padding-bottom:.4em;border-bottom:1px solid color-mix(in srgb,currentColor 18%,transparent)}h3{font-size:1.15em;margin-top:1em}h4,h5,h6{font-size:1em;margin-top:1em}
ul,ol{padding-left:1.5em;margin:0 0 1em}li{padding-left:.15em;margin-bottom:.3em}li>p{margin-bottom:.35em}
blockquote{padding:.35em 1em;font-style:italic;background:color-mix(in srgb,currentColor 4%,transparent);border-radius:0 5px 5px 0}blockquote p:last-child{margin-bottom:0}
code,kbd{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.82em;background:color-mix(in srgb,currentColor 7%,transparent);padding:.12em .3em;border-radius:3px}
pre{margin:0 0 1.2em;padding:.85em 1em;border:1px solid color-mix(in srgb,currentColor 15%,transparent);border-radius:6px;background:color-mix(in srgb,currentColor 4%,transparent);line-height:1.6;white-space:pre-wrap;overflow-wrap:anywhere;box-decoration-break:clone;-webkit-box-decoration-break:clone}pre code{padding:0;border:0;background:none}
table{width:100%;table-layout:fixed;margin:0 0 1.3em;line-height:1.6}th,td{padding:.5em .65em;border-color:color-mix(in srgb,currentColor 22%,transparent);overflow-wrap:anywhere;vertical-align:top}th{font-family:system-ui,sans-serif;font-weight:600;background:color-mix(in srgb,currentColor 7%,transparent)}tr{break-inside:avoid}th{text-align:left}.md-align-center{text-align:center}.md-align-right{text-align:right}
hr{border:0;border-top:1px solid color-mix(in srgb,currentColor 20%,transparent);margin:1.5em 0}.md-check{font-family:system-ui,sans-serif}.md-image{display:block;padding:.8em;margin:.5em 0 1em;border:1px dashed color-mix(in srgb,currentColor 25%,transparent);font-family:system-ui,sans-serif;font-size:.8em;color:inherit;opacity:.7}.md-reference{text-decoration:none}summary{font-weight:700}
`;
