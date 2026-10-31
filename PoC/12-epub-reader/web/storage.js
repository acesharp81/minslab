let connection;
export async function database() {
  if (connection) return connection;
  connection = new Promise((resolve, reject) => {
    const request = indexedDB.open('bookjari-poc12', 1);
    request.onupgradeneeded = () => {
      const db = request.result;
      db.createObjectStore('books', { keyPath: 'id' });
      db.createObjectStore('files');
      db.createObjectStore('settings');
    };
    request.onsuccess = () => { request.result.onversionchange = () => request.result.close(); resolve(request.result); };
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error('다른 책자리 탭을 닫고 다시 열어주세요.'));
  });
  return connection;
}
async function transact(stores, mode, operation) {
  const db = await database();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(stores, mode);
    let request;
    try { request = operation(transaction); } catch (error) { transaction.abort(); reject(error); return; }
    transaction.oncomplete = () => resolve(request?.result);
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error || new Error('로컬 저장을 완료하지 못했습니다.'));
  });
}
export const allBooks = () => transact(['books'], 'readonly', tx => tx.objectStore('books').getAll());
export const getFile = id => transact(['files'], 'readonly', tx => tx.objectStore('files').get(id));
export const putBook = book => transact(['books'], 'readwrite', tx => tx.objectStore('books').put(book));
export const importBook = (book, file) => transact(['books', 'files'], 'readwrite', tx => { tx.objectStore('files').put(file, book.id); return tx.objectStore('books').put(book); });
export const deleteBook = id => transact(['books', 'files'], 'readwrite', tx => { tx.objectStore('files').delete(id); return tx.objectStore('books').delete(id); });
export const getSetting = key => transact(['settings'], 'readonly', tx => tx.objectStore('settings').get(key));
export const setSetting = (key, value) => transact(['settings'], 'readwrite', tx => tx.objectStore('settings').put(value, key));
