import { Epub } from './epub.js';
import { SpreadReader } from './pagination.js';
import * as storage from './storage.js';
const $ = id => document.getElementById(id);
let books = [], current = null, epub = null, chapterIndex = 0, ready = false, busy = false;
let pager = null;
let saveTimer, toastTimer, pendingDelete, coverUrls = [];
let preferences = { fontSize: 19, theme: 'paper', columns: 2, pdfZoom: 1 };
let pdfModule;
const loadPdf = () => pdfModule ||= import('./pdf.js');
const isPdf = () => current?.format === 'pdf';
const palette = { paper: ['#fcfaf3','#30372e','#526b51'], light: ['#ffffff','#242d28','#2d5b48'], dark: ['#242c26','#e0e5da','#a8c7a1'] };
function toast(message, error = false) {
  clearTimeout(toastTimer); $('status').textContent = message; $('status').dataset.error = String(error); $('status').hidden = false;
  toastTimer = setTimeout(() => { $('status').hidden = true; }, error ? 10000 : 4500);
}
function storageError(error) {
  console.error('Local library operation failed:', error.name || 'Error');
  toast('로컬 저장을 완료하지 못했습니다. 브라우저 저장 공간과 개인정보 보호 설정을 확인해 주세요.', true);
  $('save-status').textContent = '저장 실패 · 브라우저 저장 공간을 확인하세요';
}
function create(tag, className, text) {
  const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = text; return node;
}
function setBusy(value) {
  busy = value;
  for (const id of ['import-top','import-empty','back-library','add-bookmark','prev-page','next-page','page-layout','pdf-zoom','pdf-page-input']) $(id).disabled = value;
  $('reader-loading').hidden = !value || $('reader').hidden;
  if (!value && current) updateProgress();
}
function renderShelf() {
  for (const url of coverUrls) URL.revokeObjectURL(url); coverUrls = [];
  $('shelf').replaceChildren(); $('book-count').textContent = String(books.length);
  const term = $('search').value.trim().toLocaleLowerCase();
  const visible = [...books].sort((a,b) => b.updatedAt - a.updatedAt).filter(b => `${b.title} ${b.author}`.toLocaleLowerCase().includes(term));
  $('empty').hidden = books.length > 0; $('no-results').hidden = !books.length || visible.length > 0;
  for (const book of visible) {
    const card = create('article', 'book-card'), open = create('button', 'book-open'); open.setAttribute('aria-label', `${book.title} 이어 읽기`);
    const cover = create('div', 'book-cover');
    if (book.cover) { const img = create('img'); img.alt = ''; const url = URL.createObjectURL(book.cover); coverUrls.push(url); img.src = url; cover.append(img); }
    else cover.append(create('div', 'cover-placeholder', book.title));
    open.append(cover, create('strong', '', book.title), create('span', 'author', book.author));
    const meta = create('span', 'book-meta'); meta.append(create('span', '', book.position ? `약 ${book.progress || 0}% 읽음` : '새로 담은 책'), create('span', '', `책갈피 ${book.bookmarks.length}`)); open.append(meta);
    open.onclick = () => { if (!busy) openBook(book.id); };
    const actions = create('div', 'book-actions'); actions.append(create('small', '', `${(book.size / 1024 / 1024).toFixed(1)} MB · ${book.format === 'pdf' ? `${book.pages}쪽 · PDF` : `${book.chapters}개 장 · EPUB`}`));
    const remove = create('button', 'quiet', '삭제'); remove.setAttribute('aria-label', `${book.title} 삭제`); remove.onclick = () => { if (busy) return; pendingDelete = book.id; $('delete-description').textContent = book.title; $('delete-dialog').showModal(); };
    actions.append(remove); card.append(open, actions); $('shelf').append(card);
  }
}
async function importFiles(files) {
  if (busy) return;
  if (current) { toast('서재로 돌아가 새 책을 추가해 주세요.'); return; }
  setBusy(true); let added = 0, first = null; const errors = [];
  for (const file of files) {
    let parsed;
    try {
      if (!/\.(epub|pdf)$/i.test(file.name)) throw new Error('EPUB 또는 PDF 파일만 추가할 수 있습니다.');
      if (!file.size || file.size > 50 * 1024 * 1024) throw new Error('파일당 50 MB 이하의 EPUB 또는 PDF를 선택해 주세요.');
      toast(`${file.name} 읽는 중…`);
      const buffer = await file.arrayBuffer();
      const id = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', buffer)), b => b.toString(16).padStart(2, '0')).join('');
      if (books.some(b => b.id === id)) { first ||= id; toast('이미 서재에 있는 책입니다. 기존 책갈피를 유지합니다.'); continue; }
      const format = /\.pdf$/i.test(file.name) ? 'pdf' : 'epub';
      let cover;
      if (format === 'pdf') {
        parsed = await (await loadPdf()).PdfBook.load(buffer, file.name);
        cover = await parsed.thumbnail();
      } else {
        parsed = await Epub.load(buffer);
        await parsed.chapter(0);
        cover = parsed.cover ? await (await fetch(parsed.cover)).blob() : null;
      }
      const book = { id, format, title: parsed.title, author: parsed.author, filename: file.name, size: file.size, cover, chapters: parsed.spine.length, pages: format === 'pdf' ? parsed.total : null, bookmarks: [], position: null, progress: 0, updatedAt: Date.now() };
      await storage.importBook(book, new Blob([buffer], { type: format === 'pdf' ? 'application/pdf' : 'application/epub+zip' }));
      books.push(book); added++; first ||= id;
    } catch (error) { errors.push(`${file.name}: ${error.name === 'QuotaExceededError' ? '저장 공간이 부족합니다.' : error.message}`); }
    finally { await parsed?.destroy(); }
  }
  renderShelf(); setBusy(false); $('file-input').value = '';
  if (errors.length) toast(errors.join(' / '), true);
  else if (first && files.length === 1) { await openBook(first); if (added && current) toast('책을 서재에 저장했습니다. 편안하게 읽어보세요.'); }
  else if (added) toast(`${added}권을 서재에 저장했습니다.`);
}
async function openBook(id) {
  if (busy) return;
  setBusy(true);
  let parsed;
  try {
    const book = books.find(b => b.id === id);
    const file = await storage.getFile(id);
    if (!file) throw new Error('저장된 책 파일을 찾을 수 없습니다. 원본 파일을 다시 추가해 주세요.');
    parsed = book.format === 'pdf' ? await (await loadPdf()).PdfBook.load(await file.arrayBuffer(), book.filename) : await Epub.load(await file.arrayBuffer());
    epub?.destroy(); epub = parsed; current = book;
    $('reader-title').textContent = book.title; $('reader-author').textContent = book.author;
    $('library').hidden = true; $('reader').hidden = false; document.body.classList.add('is-reading');
    $('import-top').hidden = true; $('reader-loading').hidden = false;
    document.title = `${book.title} · 책자리`;
    configureReader(); renderToc(); renderBookmarks();
    if (isPdf()) {
      pager = new (await loadPdf()).PdfReader($('pdf-pages'), epub, preferences.columns, preferences.pdfZoom, scheduleSave, error => toast(error.message, true));
      await pager.show(book.position?.page || 0); chapterIndex = 0; ready = true; updateProgress(); await savePosition();
    } else await displayChapter(Math.min(book.position?.chapter || 0, epub.spine.length - 1), book.position);
    try { await storage.setSetting('lastBook', id); } catch (error) { storageError(error); }
  } catch (error) {
    toast(error.message || '책을 열지 못했습니다.', true);
    pager?.destroy(); pager = null; await parsed?.destroy(); current = null; epub = null; ready = false;
    $('library').hidden = false; $('reader').hidden = true; document.body.classList.remove('is-reading'); $('import-top').hidden = false;
  } finally { setBusy(false); }
}
function configureReader() {
  const pdf = isPdf();
  $('book-frame').hidden = pdf; $('pdf-pages').hidden = !pdf;
  $('page-wrap').classList.toggle('is-pdf', pdf);
  for (const id of ['font-minus','font-plus','font-size']) $(id).hidden = pdf;
  $('pdf-zoom').hidden = !pdf; $('pdf-page-jump').hidden = !pdf;
  $('pdf-zoom').value = String(preferences.pdfZoom);
  if (pdf) { $('pdf-page-input').max = String(epub.total); $('chapter-label').textContent = 'PDF'; }
}
function readerStyle() {
  const [bg, fg, accent] = palette[preferences.theme];
  return `html,body{width:100%;height:100%;margin:0;overflow:hidden;background:${bg};color:${fg};color-scheme:${preferences.theme === 'dark' ? 'dark' : 'light'}}#reader-flow{box-sizing:content-box;column-fill:auto;font-family:Georgia,"Batang","Noto Serif KR",serif;font-size:${preferences.fontSize}px;line-height:1.8;overflow-wrap:anywhere}p{margin:0 0 1em;orphans:2;widows:2}h1,h2,h3,h4{line-height:1.4;margin:0 0 .8em;break-after:avoid}h1{font-size:1.7em}h2{font-size:1.4em}img{max-width:100%;max-height:calc(100vh - 64px);object-fit:contain;width:auto;height:auto;display:block;margin:0 auto 1em;break-inside:avoid}a{color:${accent};text-underline-offset:4px}pre{white-space:pre-wrap}table{max-width:100%;border-collapse:collapse;font-size:.85em}td,th{border:1px solid ${accent};padding:5px}blockquote{margin:0 0 1em;padding-left:1em;border-left:2px solid ${accent}}`;
}
async function displayChapter(index, position = null, hash = '') {
  ready = false; clearTimeout(saveTimer); pager?.destroy(); pager = null; chapterIndex = index;
  const html = await epub.chapter(index);
  const frame = $('book-frame');
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('본문을 여는 데 시간이 오래 걸립니다. 책을 다시 열어주세요.')), 15000);
    frame.onload = async () => {
      try {
        const doc = frame.contentDocument;
        await Promise.all([...doc.images].map(img => img.decode().catch(() => {})));
        await new Promise(requestAnimationFrame);
        pager = new SpreadReader(frame, preferences.columns, scheduleSave);
        pager.layout(position);
        if (hash && doc.getElementById(hash)) pager.reveal(doc.getElementById(hash));
        doc.addEventListener('click', event => {
          const link = event.target.closest('a'); if (!link) return; event.preventDefault();
          if (link.dataset.bookPath) navigate(epub.spine.findIndex(s => s.path === link.dataset.bookPath), null, link.dataset.bookHash);
        });
        doc.addEventListener('keydown', keyboard);
        attachPageGestures(doc);
        ready = true; updateProgress(); renderToc(); clearTimeout(timer); resolve();
      } catch (error) { clearTimeout(timer); reject(error); }
    };
    frame.srcdoc = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src blob:; style-src 'unsafe-inline'; script-src 'none'; connect-src 'none'; form-action 'none'; base-uri 'none'"><style id="reader-style">${readerStyle()}</style></head><body><main id="reader-flow">${html}</main></body></html>`;
  });
  $('chapter-label').textContent = epub.spine[index].label;
  await savePosition();
}
function capturePosition() {
  return { chapter: chapterIndex, ...(pager?.anchor || { ratio: 0 }) };
}
function updateProgress() {
  if (!current || !epub || !pager) return;
  const position = ready ? capturePosition() : current.position;
  const progress = Math.round((chapterIndex + (position?.ratio || 0)) / epub.spine.length * 100);
  const first = pager.page + 1, last = Math.min(pager.total, pager.page + pager.columns);
  $('progress-label').textContent = `${isPdf() ? 'PDF' : `${chapterIndex + 1}장`} · ${first === last ? first : `${first}–${last}`} / ${pager.total}쪽 · 약 ${progress}%`;
  $('left-page-number').textContent = first;
  $('right-page-number').textContent = pager.columns === 2 && first < pager.total ? first + 1 : '';
  $('page-wrap').dataset.columns = String(pager.columns);
  $('reading-progress').value = progress;
  if (isPdf()) { $('pdf-page-input').value = String(pager.anchor.page + 1); renderToc(); }
  $('prev-page').disabled = busy || (chapterIndex === 0 && pager.page === 0);
  $('next-page').disabled = busy || (chapterIndex === epub.spine.length - 1 && pager.page + pager.columns >= pager.total);
}
async function turnPage(direction) {
  if (!ready || busy || !pager) return;
  if (isPdf()) { const target = pager.page + direction * pager.columns; if (target >= 0 && target < pager.total) await navigate(0, { page: target }); return; }
  if (!pager.turn(direction)) navigate(chapterIndex + direction, direction < 0 ? { end: true } : null);
}
function attachPageGestures(doc) {
  let lastWheel = 0, distance = 0, touch = null;
  doc.addEventListener('wheel', event => {
    if (event.ctrlKey || event.metaKey || (isPdf() && preferences.pdfZoom > 1)) return;
    event.preventDefault();
    if (Date.now() - lastWheel < 400) return;
    distance += Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
    if (Math.abs(distance) >= 45) { turnPage(Math.sign(distance)); distance = 0; lastWheel = Date.now(); }
  }, { passive: false });
  doc.addEventListener('touchstart', event => { if (event.touches.length === 1) touch = { x: event.touches[0].clientX, y: event.touches[0].clientY }; }, { passive: true });
  doc.addEventListener('touchend', event => {
    if (!touch || !event.changedTouches.length || (isPdf() && preferences.pdfZoom > 1)) return;
    const dx = event.changedTouches[0].clientX - touch.x, dy = event.changedTouches[0].clientY - touch.y;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.4) turnPage(dx < 0 ? 1 : -1);
    touch = null;
  }, { passive: true });
}
async function savePosition() {
  clearTimeout(saveTimer);
  if (!current || !ready) return;
  const position = capturePosition();
  current.position = position; current.progress = Math.round((position.chapter + position.ratio) / epub.spine.length * 100); current.updatedAt = Date.now();
  try { await storage.putBook(structuredClone(current)); $('save-status').textContent = '이 브라우저에 읽던 위치 저장됨'; }
  catch (error) { storageError(error); }
}
function scheduleSave() {
  if (!ready) return;
  updateProgress(); clearTimeout(saveTimer);
  $('save-status').textContent = '읽던 위치 저장 중…'; savePosition();
}
async function navigate(index, position = null, hash = '') {
  if (busy || !epub || index < 0 || index >= epub.spine.length) return;
  setBusy(true); await savePosition();
  try {
    if (isPdf()) await pager.show(position?.page ?? 0); else await displayChapter(index, position, hash);
    toggleSidebar(false);
  }
  catch (error) { if (!isPdf()) ready = false; toast(error.message, true); }
  finally { setBusy(false); }
}
function renderToc() {
  $('toc-panel').replaceChildren(); if (!epub) return;
  if (isPdf()) {
    for (const item of epub.toc) {
      const button = create('button', 'toc-item', item.label);
      button.title = `${item.page + 1}쪽`; button.style.paddingLeft = `${10 + item.depth * 10}px`;
      button.setAttribute('aria-current', String(item.page >= pager?.page && item.page < pager?.page + pager?.columns));
      button.onclick = () => navigate(0, { page: item.page }); $('toc-panel').append(button);
    }
    return;
  }
  for (const item of epub.toc) {
    const index = epub.spine.findIndex(s => s.path === item.path);
    const button = create('button', 'toc-item', item.label || epub.spine[index].label);
    button.setAttribute('aria-current', String(index === chapterIndex)); button.onclick = () => navigate(index, null, item.hash); $('toc-panel').append(button);
  }
}
function renderBookmarks() {
  $('marks-panel').replaceChildren(); $('mark-count').textContent = String(current?.bookmarks.length || 0);
  if (!current?.bookmarks.length) { $('marks-panel').append(create('p', 'bookmark-go', '기억하고 싶은 문장에서 ‘＋ 책갈피’를 눌러주세요.')); return; }
  for (const mark of [...current.bookmarks].sort((a,b) => isPdf() ? a.position.page - b.position.page : a.position.chapter - b.position.chapter || a.position.ratio - b.position.ratio)) {
    const item = create('div', 'bookmark-item'), go = create('button', 'bookmark-go');
    go.append(create('strong', '', mark.label), create('small', '', `${isPdf() ? `${mark.position.page + 1}쪽` : `${mark.position.chapter + 1}장`} · ${new Date(mark.createdAt).toLocaleDateString('ko-KR')}`)); go.onclick = () => navigate(mark.position.chapter, mark.position);
    const remove = create('button', 'quiet bookmark-delete', '책갈피 삭제');
    remove.onclick = async () => {
      if (busy) return;
      setBusy(true); const old = current.bookmarks; current.bookmarks = old.filter(m => m.id !== mark.id);
      try { await storage.putBook(structuredClone(current)); renderBookmarks(); toast('책갈피를 삭제했습니다.'); }
      catch (error) { current.bookmarks = old; storageError(error); }
      finally { setBusy(false); }
    };
    item.append(go, remove); $('marks-panel').append(item);
  }
}
async function addBookmark() {
  if (!ready || busy) return;
  const position = capturePosition();
  if (current.bookmarks.some(m => isPdf() ? m.position.page === position.page : m.position.chapter === position.chapter && m.position.block === position.block && (m.position.textOffset ?? 0) === (position.textOffset ?? 0))) { toast('이 위치에 이미 책갈피가 있습니다.'); return; }
  const mark = { id: crypto.randomUUID(), position, label: position.excerpt || epub.spine[chapterIndex].label, createdAt: Date.now() };
  current.bookmarks.push(mark); setBusy(true);
  try { await storage.putBook(structuredClone(current)); renderBookmarks(); toast('책갈피를 저장했습니다.'); }
  catch (error) { current.bookmarks = current.bookmarks.filter(m => m.id !== mark.id); storageError(error); }
  finally { setBusy(false); }
}
function toggleSidebar(value = $('sidebar').hidden) { $('sidebar').hidden = !value; $('toggle-sidebar').setAttribute('aria-expanded', String(value)); }
function selectTab(marks) {
  $('toc-panel').hidden = marks; $('marks-panel').hidden = !marks;
  $('toc-tab').setAttribute('aria-selected', String(!marks)); $('marks-tab').setAttribute('aria-selected', String(marks));
}
async function updatePreferences() {
  const position = ready ? capturePosition() : null;
  document.documentElement.dataset.theme = preferences.theme; $('font-size').value = String(preferences.fontSize); $('theme').value = preferences.theme; $('page-layout').value = String(preferences.columns);
  $('font-minus').disabled = preferences.fontSize <= 14; $('font-plus').disabled = preferences.fontSize >= 30;
  if (isPdf() && pager) {
    setBusy(true);
    try { pager.columns = preferences.columns; pager.zoom = preferences.pdfZoom; await pager.layout(position); }
    catch (error) { toast(error.message, true); }
    finally { setBusy(false); }
  }
  const style = !isPdf() && $('book-frame').contentDocument?.getElementById('reader-style');
  if (style && pager) { style.textContent = readerStyle(); pager.columns = preferences.columns; pager.layout(position); updateProgress(); scheduleSave(); }
  try { await storage.setSetting('preferences', preferences); } catch (error) { storageError(error); }
}
function keyboard(event) {
  if (event.altKey || event.ctrlKey || event.metaKey || /INPUT|TEXTAREA|SELECT|BUTTON/.test(event.target.tagName)) return;
  if (!$('reader').hidden && ['ArrowRight', 'PageDown', ' '].includes(event.key)) { event.preventDefault(); turnPage(1); }
  if (!$('reader').hidden && ['ArrowLeft', 'PageUp'].includes(event.key)) { event.preventDefault(); turnPage(-1); }
}
$('import-top').onclick = $('import-empty').onclick = () => $('file-input').click();
$('file-input').onchange = event => importFiles([...event.target.files]);
$('search').oninput = renderShelf;
$('back-library').onclick = async () => {
  if (busy) return;
  setBusy(true); await savePosition(); ready = false; clearTimeout(saveTimer); pager?.destroy(); pager = null; epub?.destroy(); epub = null; current = null;
  $('book-frame').onload = null; $('book-frame').srcdoc = ''; $('library').hidden = false; $('reader').hidden = true; document.body.classList.remove('is-reading'); $('import-top').hidden = false;
  document.title = '책자리 · EPUB · PDF 리더';
  try { await storage.setSetting('lastBook', null); } catch (error) { storageError(error); }
  renderShelf(); setBusy(false); $('import-top').focus();
};
document.querySelector('.brand').onclick = event => { event.preventDefault(); if (current && !busy) $('back-library').click(); };
$('add-bookmark').onclick = addBookmark;
$('prev-page').onclick = () => turnPage(-1); $('next-page').onclick = () => turnPage(1);
$('toggle-sidebar').onclick = () => toggleSidebar(); $('toc-tab').onclick = () => selectTab(false); $('marks-tab').onclick = () => selectTab(true);
$('font-minus').onclick = () => { preferences.fontSize = Math.max(14, preferences.fontSize - 1); updatePreferences(); };
$('font-plus').onclick = () => { preferences.fontSize = Math.min(30, preferences.fontSize + 1); updatePreferences(); };
$('pdf-zoom').onchange = event => { preferences.pdfZoom = Number(event.target.value); updatePreferences(); };
$('pdf-page-jump').onsubmit = event => { event.preventDefault(); if ($('pdf-page-input').checkValidity()) navigate(0, { page: Number($('pdf-page-input').value) - 1 }); };
attachPageGestures($('pdf-pages'));
$('page-layout').onchange = event => { preferences.columns = Number(event.target.value); updatePreferences(); };
$('theme').onchange = event => { preferences.theme = event.target.value; updatePreferences(); };
$('delete-cancel').onclick = () => $('delete-dialog').close();
$('delete-confirm').onclick = async () => {
  $('delete-confirm').disabled = true;
  try { await storage.deleteBook(pendingDelete); books = books.filter(b => b.id !== pendingDelete); renderShelf(); $('delete-dialog').close(); toast('서재에서 책을 삭제했습니다.'); }
  catch (error) { storageError(error); }
  finally { $('delete-confirm').disabled = false; }
};
let dragDepth = 0;
document.addEventListener('dragenter', event => { if ([...event.dataTransfer.types].includes('Files')) { event.preventDefault(); dragDepth++; $('drop-overlay').hidden = false; } });
document.addEventListener('dragover', event => { if ([...event.dataTransfer.types].includes('Files')) event.preventDefault(); });
document.addEventListener('dragleave', () => { if (--dragDepth <= 0) { dragDepth = 0; $('drop-overlay').hidden = true; } });
document.addEventListener('drop', event => { event.preventDefault(); dragDepth = 0; $('drop-overlay').hidden = true; if (event.dataTransfer.files.length) importFiles([...event.dataTransfer.files]); });
document.addEventListener('keydown', keyboard);
document.addEventListener('visibilitychange', () => { if (document.hidden) savePosition(); });
window.addEventListener('pagehide', savePosition);
async function start() {
  try {
    const prefs = await storage.getSetting('preferences');
    if (prefs) preferences = { fontSize: Math.max(14, Math.min(30, Number(prefs.fontSize) || 19)), theme: palette[prefs.theme] ? prefs.theme : 'paper', columns: prefs.columns === 1 ? 1 : 2, pdfZoom: [1, 1.25, 1.5, 2].includes(prefs.pdfZoom) ? prefs.pdfZoom : 1 };
    await updatePreferences(); books = await storage.allBooks(); renderShelf();
    const last = await storage.getSetting('lastBook'); if (last && books.some(b => b.id === last)) await openBook(last);
  } catch (error) { storageError(error); }
}
start();
