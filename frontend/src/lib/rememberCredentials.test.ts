import assert from 'node:assert/strict';
import {
  clearRememberedCredentials,
  loadRememberedCredentials,
  saveRememberedCredentials,
} from './rememberCredentials';

type Store = Record<string, string>;

function createStorage() {
  const store: Store = {};
  return {
    getItem(key: string) {
      return store[key] ?? null;
    },
    setItem(key: string, value: string) {
      store[key] = value;
    },
    removeItem(key: string) {
      delete store[key];
    },
    snapshot() {
      return { ...store };
    },
  };
}

{
  const storage = createStorage();
  saveRememberedCredentials(storage, { username: 'admin', password: 'admin' });

  assert.deepEqual(loadRememberedCredentials(storage), {
    remember: true,
    username: 'admin',
    password: 'admin',
  });
}

{
  const storage = createStorage();
  const previous = globalThis.localStorage;
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: storage,
  });

  try {
    saveRememberedCredentials({ username: 'admin', password: 'admin' });

    assert.deepEqual(loadRememberedCredentials(storage), {
      remember: true,
      username: 'admin',
      password: 'admin',
    });
  } finally {
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      value: previous,
    });
  }
}

{
  const storage = createStorage();
  saveRememberedCredentials(storage, { username: 'admin', password: 'admin' });
  clearRememberedCredentials(storage);

  assert.deepEqual(loadRememberedCredentials(storage), {
    remember: false,
    username: '',
    password: '',
  });
}
