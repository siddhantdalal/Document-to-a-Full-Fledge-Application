const DB_NAME = "doc-to-app";
const STORE = "secrets";
const MASTER_KEY_ID = "encryption-key";
const STORAGE_KEY = "doc-to-app:provider-key";

export interface StoredKey {
  provider: string;
  key: string;
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function idbGet<T>(db: IDBDatabase, id: string): Promise<T | undefined> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).get(id);
    req.onsuccess = () => resolve(req.result as T | undefined);
    req.onerror = () => reject(req.error);
  });
}

function idbPut(db: IDBDatabase, id: string, value: unknown): Promise<void> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    const req = tx.objectStore(STORE).put(value, id);
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
  });
}

async function getMasterKey(): Promise<CryptoKey> {
  const db = await openDB();
  const existing = await idbGet<CryptoKey>(db, MASTER_KEY_ID);
  if (existing) return existing;
  const key = await crypto.subtle.generateKey(
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
  await idbPut(db, MASTER_KEY_ID, key);
  return key;
}

export async function saveKey(provider: string, apiKey: string): Promise<void> {
  if (!apiKey) {
    clearKey();
    return;
  }
  const master = await getMasterKey();
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    master,
    new TextEncoder().encode(apiKey),
  );
  const payload = JSON.stringify({
    v: 1,
    provider,
    iv: Array.from(iv),
    ct: Array.from(new Uint8Array(ciphertext)),
  });
  localStorage.setItem(STORAGE_KEY, payload);
}

export async function loadKey(): Promise<StoredKey | null> {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    const { provider, iv, ct } = JSON.parse(raw) as {
      provider: string;
      iv: number[];
      ct: number[];
    };
    const master = await getMasterKey();
    const plaintext = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: new Uint8Array(iv) },
      master,
      new Uint8Array(ct),
    );
    return { provider, key: new TextDecoder().decode(plaintext) };
  } catch {
    clearKey();
    return null;
  }
}

export function clearKey(): void {
  localStorage.removeItem(STORAGE_KEY);
}

export function hasStoredKey(): boolean {
  return localStorage.getItem(STORAGE_KEY) !== null;
}
