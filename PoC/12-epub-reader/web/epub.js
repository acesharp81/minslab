/* EPUB 2/3 container, package, navigation and isolated reflowable chapter renderer. */
const MAX_TOTAL = 150 * 1024 * 1024;
const parser = new DOMParser();
function xml(text) {
  const doc = parser.parseFromString(text, 'application/xml');
  if (doc.querySelector('parsererror')) throw new Error('EPUB의 문서 구조를 읽을 수 없습니다.');
  return doc;
}
const nodes = (root, name) => Array.from(root.getElementsByTagNameNS('*', name));
const textOf = (root, name) => nodes(root, name)[0]?.textContent?.trim() || '';
export function resolvePath(base, href) {
  if (!href || /^(?:[a-z][\w+.-]*:|\/\/)/i.test(href)) return null;
  try {
    const url = new URL(href, 'https://epub.invalid/' + base);
    if (url.origin !== 'https://epub.invalid') return null;
    return { path: decodeURIComponent(url.pathname.slice(1)), hash: decodeURIComponent(url.hash.slice(1)) };
  } catch { return null; }
}
export class Epub {
  constructor(zip) { this.zip = zip; this.urls = new Map(); this.spine = []; this.toc = []; }
  static async load(buffer) {
    let zip;
    try { zip = await JSZip.loadAsync(buffer); } catch { throw new Error('유효한 EPUB 파일이 아닙니다. 파일을 확인해 주세요.'); }
    const entries = Object.values(zip.files);
    if (entries.length > 5000 || entries.reduce((n, e) => n + (e._data?.uncompressedSize || 0), 0) > MAX_TOTAL) {
      throw new Error('압축을 푼 책의 크기가 너무 큽니다. 150 MB 이하의 EPUB을 선택해 주세요.');
    }
    const book = new Epub(zip);
    try { await book.init(); return book; } catch (error) { book.destroy(); throw error; }
  }
  async read(path) {
    const file = this.zip.file(path);
    if (!file) throw new Error('책에 필요한 파일이 없습니다: ' + path);
    if ((file._data?.uncompressedSize || 0) > 8 * 1024 * 1024) throw new Error('한 장의 크기가 너무 커서 열 수 없습니다.');
    return file.async('string');
  }
  async init() {
    const container = xml(await this.read('META-INF/container.xml'));
    this.packagePath = nodes(container, 'rootfile')[0]?.getAttribute('full-path');
    if (!this.packagePath) throw new Error('EPUB 패키지 정보를 찾을 수 없습니다.');
    const opf = xml(await this.read(this.packagePath));
    this.title = textOf(opf, 'title') || '제목 없는 책';
    this.author = nodes(opf, 'creator').map(n => n.textContent.trim()).join(', ') || '저자 미상';
    this.manifest = new Map();
    for (const item of nodes(opf, 'item')) {
      const resolved = resolvePath(this.packagePath, item.getAttribute('href'));
      if (resolved) this.manifest.set(item.getAttribute('id'), { path: resolved.path, type: item.getAttribute('media-type'), properties: (item.getAttribute('properties') || '').split(/\s+/) });
    }
    for (const itemref of nodes(opf, 'itemref')) {
      const item = this.manifest.get(itemref.getAttribute('idref'));
      if (item && ['application/xhtml+xml', 'text/html'].includes(item.type)) this.spine.push({ ...item });
    }
    if (!this.spine.length) throw new Error('읽을 수 있는 본문이 없습니다. DRM이 없는 EPUB 파일을 선택해 주세요.');
    if (this.zip.file('META-INF/encryption.xml')) {
      const encrypted = xml(await this.read('META-INF/encryption.xml'));
      if (nodes(encrypted, 'CipherReference').some(n => this.spine.some(s => s.path === n.getAttribute('URI')))) {
        throw new Error('DRM으로 암호화된 책은 열 수 없습니다. DRM이 없는 EPUB을 선택해 주세요.');
      }
    }
    const nav = [...this.manifest.values()].find(item => item.properties.includes('nav'));
    if (nav) {
      const doc = xml(await this.read(nav.path));
      const root = nodes(doc, 'nav').find(n => (n.getAttribute('epub:type') || n.getAttributeNS('http://www.idpf.org/2007/ops', 'type') || '').split(/\s+/).includes('toc')) || nodes(doc, 'nav')[0];
      if (root) for (const a of nodes(root, 'a')) {
        const target = resolvePath(nav.path, a.getAttribute('href'));
        if (target && this.spine.some(s => s.path === target.path)) this.toc.push({ ...target, label: a.textContent.trim() });
      }
    }
    if (!this.toc.length) {
      const ncx = this.manifest.get(nodes(opf, 'spine')[0]?.getAttribute('toc')) || [...this.manifest.values()].find(i => i.type === 'application/x-dtbncx+xml');
      if (ncx) {
        const doc = xml(await this.read(ncx.path));
        for (const point of nodes(doc, 'navPoint')) {
          const target = resolvePath(ncx.path, nodes(point, 'content')[0]?.getAttribute('src'));
          if (target && this.spine.some(s => s.path === target.path)) this.toc.push({ ...target, label: textOf(point, 'text') });
        }
      }
    }
    this.spine.forEach((s, index) => { s.label = this.toc.find(t => t.path === s.path)?.label || `${index + 1}장`; });
    if (!this.toc.length) this.toc = this.spine.map(s => ({ path: s.path, hash: '', label: s.label }));
    const coverId = nodes(opf, 'meta').find(n => n.getAttribute('name') === 'cover')?.getAttribute('content');
    const cover = [...this.manifest.values()].find(i => i.properties.includes('cover-image')) || this.manifest.get(coverId);
    this.cover = cover ? await this.asset(cover.path) : null;
  }
  async asset(path) {
    if (this.urls.has(path)) return this.urls.get(path);
    const entry = this.zip.file(path);
    const ext = path.split('.').pop().toLowerCase();
    const type = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', webp: 'image/webp', avif: 'image/avif', svg: 'image/svg+xml' }[ext];
    if (!entry || !type || (entry._data?.uncompressedSize || 0) > 15 * 1024 * 1024) return null;
    let data;
    if (ext === 'svg') {
      const clean = DOMPurify.sanitize(await entry.async('string'), { USE_PROFILES: { svg: true, svgFilters: true }, FORBID_TAGS: ['style', 'foreignObject', 'a', 'image', 'use', 'animate', 'set'], FORBID_ATTR: ['style'] });
      data = new Blob([clean], { type });
    } else data = new Blob([await entry.async('uint8array')], { type });
    const url = URL.createObjectURL(data); this.urls.set(path, url); return url;
  }
  async chapter(index) {
    const section = this.spine[index];
    if (!section) throw new Error('해당 장을 찾을 수 없습니다.');
    const raw = await this.read(section.path);
    // EPUB content never joins the application DOM. Discard publisher CSS, events,
    // scripts, forms, embedded frames and external resources before rendering.
    const body = DOMPurify.sanitize(raw, {
      RETURN_DOM: true, USE_PROFILES: { html: true, svg: true },
      FORBID_TAGS: ['script', 'style', 'link', 'meta', 'base', 'iframe', 'object', 'embed', 'form', 'input', 'button', 'textarea', 'select', 'audio', 'video', 'source', 'foreignObject', 'use', 'animate', 'set'],
      FORBID_ATTR: ['style', 'srcset', 'target', 'action', 'poster', 'background', 'autofocus'],
    });
    for (const svg of body.querySelectorAll('svg')) {
      const image = svg.querySelector('image');
      if (image) {
        const img = document.createElement('img');
        img.setAttribute('src', image.getAttribute('href') || image.getAttribute('xlink:href') || '');
        img.alt = svg.querySelector('title')?.textContent || '책 삽화';
        svg.replaceWith(img);
      } else svg.remove();
    }
    for (const element of body.querySelectorAll('*')) {
      const src = element.getAttribute('src');
      const href = element.getAttribute('href');
      for (const attribute of [...element.attributes]) {
        if (!['id', 'lang', 'dir', 'alt', 'title', 'colspan', 'rowspan', 'start'].includes(attribute.name)) element.removeAttribute(attribute.name);
      }
      if (element.tagName === 'IMG') {
        const target = resolvePath(section.path, src);
        const url = target ? await this.asset(target.path) : null;
        if (url) element.setAttribute('src', url);
        else { element.remove(); continue; }
      }
      if (element.tagName === 'A' && href) {
        const target = resolvePath(section.path, href);
        if (target && this.spine.some(s => s.path === target.path)) {
          element.setAttribute('href', '#'); element.dataset.bookPath = target.path; element.dataset.bookHash = target.hash;
        }
      }
    }
    body.querySelectorAll('p,h1,h2,h3,h4,h5,h6,li,blockquote,pre,table,img').forEach((el, i) => { el.dataset.readerBlock = String(i); });
    return body.innerHTML;
  }
  destroy() { for (const url of this.urls.values()) URL.revokeObjectURL(url); this.urls.clear(); }
}
