// Reflow each chapter into fixed-height columns. Two adjacent columns form a spread.
export class SpreadReader {
  constructor(frame, columns, onChange) {
    this.frame = frame; this.doc = frame.contentDocument;
    this.flow = this.doc.body.firstElementChild;
    this.columns = columns; this.page = 0; this.total = 1; this.shift = 0;
    this.onChange = onChange; this.anchor = null;
    this.observer = new ResizeObserver(() => {
      if (this.width !== frame.clientWidth || this.height !== frame.clientHeight) {
        this.layout(this.anchor); this.onChange();
      }
    });
    this.observer.observe(frame);
  }
  destroy() { this.observer.disconnect(); }
  layout(position = null) {
    this.width = this.frame.clientWidth; this.height = this.frame.clientHeight;
    this.padding = this.width < 600 ? 16 : 34;
    this.pitch = this.width / this.columns;
    const gutter = this.padding * 2;
    Object.assign(this.flow.style, {
      width: `${this.width - gutter}px`, height: `${Math.max(100, this.height - 48)}px`,
      margin: `24px ${this.padding}px`, columnWidth: `${this.pitch - gutter}px`,
      columnCount: String(this.columns), columnGap: `${gutter}px`, transform: 'none',
    });
    this.shift = 0;
    const range = this.doc.createRange(); range.selectNodeContents(this.flow);
    const right = Array.from(range.getClientRects()).reduce((max, r) => r.width && r.height ? Math.max(max, r.right) : max, this.padding);
    this.total = Math.max(1, Math.ceil((right - this.padding + gutter - 1) / this.pitch));
    this.restore(position);
  }
  show(page) {
    const last = Math.floor((this.total - 1) / this.columns) * this.columns;
    this.page = Math.max(0, Math.min(last, Math.floor(page / this.columns) * this.columns));
    this.shift = this.page * this.pitch;
    this.flow.style.transform = `translateX(${-this.shift}px)`;
    this.doc.documentElement.dataset.columns = String(this.columns);
    this.frame.dataset.page = String(this.page + 1);
    this.frame.dataset.pages = String(this.total);
    this.frame.dataset.columns = String(this.columns);
    this.anchor = this.capture();
  }
  turn(direction) {
    const target = this.page + direction * this.columns;
    if (target < 0 || target >= this.total) return false;
    this.show(target); this.onChange(); return true;
  }
  visible(rect) { return rect.width > 0 && rect.height > 0 && rect.right > 0 && rect.left < this.width && rect.bottom > 0 && rect.top < this.height; }
  capture() {
    const walker = this.doc.createTreeWalker(this.flow, NodeFilter.SHOW_TEXT);
    let node, block, textOffset = 0, excerpt = '';
    while ((node = walker.nextNode())) {
      if (!node.textContent.trim()) continue;
      const range = this.doc.createRange(); range.selectNodeContents(node);
      if (![...range.getClientRects()].some(r => this.visible(r))) continue;
      // Find the first character on this spread, including paragraphs spanning pages.
      let lo = 0, hi = node.length;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        range.setStart(node, mid); range.setEnd(node, Math.min(node.length, mid + 1));
        if (range.getBoundingClientRect().right > 0) hi = mid; else lo = mid + 1;
      }
      block = node.parentElement.closest('[data-reader-block]');
      if (block) {
        const prefix = this.doc.createRange(); prefix.selectNodeContents(block); prefix.setEnd(node, lo);
        textOffset = prefix.toString().length;
        excerpt = block.textContent.slice(textOffset).trim().slice(0, 90);
      }
      break;
    }
    if (!block) block = [...this.flow.querySelectorAll('[data-reader-block]')].find(el => [...el.getClientRects()].some(r => this.visible(r)));
    return { block: block?.dataset.readerBlock ?? null, textOffset, excerpt: excerpt || block?.textContent.trim().slice(0, 90) || '', ratio: Math.min(1, (this.page + this.columns) / this.total), page: this.page, layout: 'pages' };
  }
  blockRect(element, offset = 0) {
    const walker = this.doc.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (offset < node.length) {
        const range = this.doc.createRange(); range.setStart(node, offset); range.setEnd(node, Math.min(node.length, offset + 1));
        return range.getBoundingClientRect();
      }
      offset -= node.length;
    }
    return element.getClientRects()[0] || element.getBoundingClientRect();
  }
  reveal(element, offset = 0) {
    const rect = this.blockRect(element, offset);
    this.show(Math.max(0, Math.floor((rect.left + this.shift - this.padding + 1) / this.pitch)));
    if (element.dataset.readerBlock != null) {
      this.anchor = { ...this.anchor, block: element.dataset.readerBlock, textOffset: offset, excerpt: element.textContent.slice(offset).trim().slice(0, 90) };
    }
  }
  restore(position) {
    if (position?.end) { this.show(this.total - 1); return; }
    const block = position?.block != null ? [...this.flow.querySelectorAll('[data-reader-block]')].find(el => el.dataset.readerBlock === position.block) : null;
    if (block) {
      // Existing scroll-mode bookmarks still point to the same paragraph.
      const offset = position.textOffset ?? Math.floor(Math.max(0, Math.min(1, position.offset || 0)) * Math.max(0, block.textContent.length - 1));
      this.reveal(block, offset);
    } else this.show(position ? Math.floor((position.ratio || 0) * Math.max(0, this.total - this.columns)) : 0);
  }
}
