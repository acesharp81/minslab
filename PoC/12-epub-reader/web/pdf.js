import * as pdfjs from './vendor/pdfjs/legacy/build/pdf.min.mjs';
const assets = new URL('./vendor/pdfjs/', import.meta.url);
pdfjs.GlobalWorkerOptions.workerSrc = new URL('legacy/build/pdf.worker.min.mjs', assets).href;

export class PdfBook {
  static async load(buffer, filename = '문서.pdf') {
    const task = pdfjs.getDocument({
      // PDF.js transfers this copy to its worker; keep the original for IndexedDB.
      data: new Uint8Array(buffer.slice(0)), isEvalSupported: false, enableXfa: false,
      cMapUrl: new URL('cmaps/', assets).href, cMapPacked: true,
      standardFontDataUrl: new URL('standard_fonts/', assets).href,
      wasmUrl: new URL('wasm/', assets).href, iccUrl: new URL('iccs/', assets).href,
    });
    try {
      const document = await task.promise;
      const book = new PdfBook(document, task);
      const meta = await document.getMetadata().catch(() => null);
      book.title = meta?.info?.Title?.trim() || filename.replace(/\.pdf$/i, '');
      book.author = meta?.info?.Author?.trim() || '저자 미상';
      book.spine = [{ path: 'pdf', label: book.title }];
      await book.navigation();
      return book;
    } catch (error) {
      await task.destroy();
      if (error.name === 'PasswordException') throw new Error('암호로 보호된 PDF입니다. 암호가 해제된 파일을 추가해 주세요.');
      throw new Error('유효한 PDF 파일을 읽을 수 없습니다. 손상되지 않은 파일을 확인해 주세요.');
    }
  }
  constructor(document, task) { this.task = task; this.document = document; this.total = document.numPages; this.toc = []; }
  async navigation() {
    const outline = await this.document.getOutline().catch(() => null);
    const walk = async (items, depth = 0) => {
      for (const item of items || []) {
        try {
          const dest = typeof item.dest === 'string' ? await this.document.getDestination(item.dest) : item.dest;
          if (dest?.length) {
            const page = typeof dest[0] === 'number' ? dest[0] : await this.document.getPageIndex(dest[0]);
            if (page >= 0 && page < this.total) this.toc.push({ label: item.title || `${page + 1}쪽`, page, depth });
          }
        } catch { /* Ignore broken outline destinations; page jump is always available. */ }
        if (depth < 20) await walk(item.items, depth + 1);
      }
    };
    await walk(outline);
    if (!this.toc.length) {
      const step = Math.max(1, Math.ceil(this.total / 200));
      for (let page = 0; page < this.total; page += step) this.toc.push({ label: `${page + 1}쪽`, page, depth: 0 });
    }
  }
  async thumbnail() {
    const page = await this.document.getPage(1), base = page.getViewport({ scale: 1 });
    const viewport = page.getViewport({ scale: Math.min(240 / base.width, 320 / base.height) });
    const canvas = document.createElement('canvas'); canvas.width = Math.ceil(viewport.width); canvas.height = Math.ceil(viewport.height);
    await page.render({ canvas, viewport, annotationMode: pdfjs.AnnotationMode.DISABLE }).promise;
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
    page.cleanup(); canvas.width = canvas.height = 0; return blob;
  }
  destroy() { return this.task.destroy(); }
}

export class PdfReader {
  constructor(container, book, columns, zoom, onChange, onError) {
    this.container = container; this.book = book; this.total = book.total;
    this.columns = columns; this.zoom = zoom; this.page = 0; this.targetPage = 0;
    this.anchor = { page: 0, ratio: Math.min(columns, this.total) / this.total, format: 'pdf', excerpt: '1쪽' };
    this.tasks = new Set(); this.generation = 0; this.destroyed = false;
    this.onChange = onChange; this.onError = onError;
    this.width = container.clientWidth; this.height = container.clientHeight;
    this.observer = new ResizeObserver(() => {
      if (this.destroyed || !container.clientWidth || !container.clientHeight) return;
      if (this.width !== container.clientWidth || this.height !== container.clientHeight) {
        clearTimeout(this.resizeTimer);
        this.resizeTimer = setTimeout(() => this.show(this.targetPage).catch(onError), 100);
      }
    });
    this.observer.observe(container);
  }
  async show(page) {
    const target = Math.max(0, Math.min(this.total - 1, Math.floor(Number(page) || 0)));
    this.targetPage = target;
    const start = Math.floor(target / this.columns) * this.columns;
    const generation = ++this.generation;
    for (const task of this.tasks) task.cancel(); this.tasks.clear();
    this.width = this.container.clientWidth; this.height = this.container.clientHeight;
    const cellWidth = Math.max(50, this.width / this.columns - 16), cellHeight = Math.max(100, this.height - 32);
    const spread = document.createElement('div'); spread.className = 'pdf-spread';
    spread.style.gridTemplateColumns = `repeat(${this.columns}, minmax(0, 1fr))`;
    spread.style.width = `${this.width * this.zoom}px`;
    spread.style.minHeight = `${this.height * this.zoom}px`;
    try {
      for (let index = start; index < start + this.columns; index++) {
        const slot = document.createElement('div'); slot.className = 'pdf-sheet'; spread.append(slot);
        if (index >= this.total) { slot.classList.add('pdf-blank'); slot.setAttribute('aria-label', '빈 페이지'); continue; }
        const pdfPage = await this.book.document.getPage(index + 1);
        if (this.destroyed || generation !== this.generation) return false;
        const base = pdfPage.getViewport({ scale: 1 });
        const viewport = pdfPage.getViewport({ scale: Math.min(cellWidth / base.width, cellHeight / base.height) * this.zoom });
        const canvas = document.createElement('canvas');
        const outputScale = Math.min(window.devicePixelRatio || 1, 2, Math.sqrt(4_000_000 / (viewport.width * viewport.height)));
        canvas.width = Math.max(1, Math.ceil(viewport.width * outputScale)); canvas.height = Math.max(1, Math.ceil(viewport.height * outputScale));
        canvas.style.width = `${viewport.width}px`; canvas.style.height = `${viewport.height}px`;
        canvas.dataset.pageNumber = String(index + 1); canvas.setAttribute('role', 'img'); canvas.setAttribute('aria-label', `${this.book.title} ${index + 1}쪽`);
        const task = pdfPage.render({ canvas, viewport, transform: [outputScale, 0, 0, outputScale, 0, 0], annotationMode: pdfjs.AnnotationMode.DISABLE });
        this.tasks.add(task);
        try { await task.promise; } finally { this.tasks.delete(task); }
        const text = await pdfPage.getTextContent().catch(() => null);
        const description = document.createElement('span'); description.className = 'sr-only';
        description.textContent = text?.items?.filter(item => 'str' in item).map(item => item.str).join(' ') || '텍스트가 없는 이미지 페이지';
        slot.append(canvas, description); pdfPage.cleanup();
      }
      if (this.destroyed || generation !== this.generation) return false;
      this.container.replaceChildren(spread); this.container.scrollTo(0, 0);
      this.page = start;
      this.anchor = { page: target, ratio: Math.min(1, (start + this.columns) / this.total), format: 'pdf', excerpt: `${target + 1}쪽` };
      this.container.dataset.page = String(start + 1); this.container.dataset.pages = String(this.total); this.container.dataset.columns = String(this.columns);
      this.onChange(); return true;
    } catch (error) {
      if (this.destroyed || generation !== this.generation || error.name === 'RenderingCancelledException') return false;
      throw new Error('PDF 페이지를 표시하지 못했습니다. 다른 페이지를 선택하거나 책을 다시 열어주세요.');
    }
  }
  async layout(position) { return this.show(position?.page ?? this.targetPage); }
  destroy() {
    this.destroyed = true; this.generation++; clearTimeout(this.resizeTimer); this.observer.disconnect();
    for (const task of this.tasks) task.cancel(); this.tasks.clear();
    this.container.replaceChildren();
  }
}
