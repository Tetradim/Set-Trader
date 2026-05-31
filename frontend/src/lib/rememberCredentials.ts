type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

const REMEMBER_CREDENTIALS_KEY = 'sentinel_remember_credentials_v1';

export type RememberedCredentials = {
  remember: boolean;
  username: string;
  password: string;
};

function getStorage(): StorageLike | null {
  if (typeof localStorage === 'undefined') return null;
  return localStorage;
}

function emptyCredentials(): RememberedCredentials {
  return { remember: false, username: '', password: '' };
}

export function loadRememberedCredentials(storage: StorageLike | null = getStorage()): RememberedCredentials {
  if (!storage) return emptyCredentials();

  try {
    const raw = storage.getItem(REMEMBER_CREDENTIALS_KEY);
    if (!raw) return emptyCredentials();

    const parsed = JSON.parse(raw);
    if (
      parsed?.remember !== true ||
      typeof parsed.username !== 'string' ||
      typeof parsed.password !== 'string'
    ) {
      return emptyCredentials();
    }

    return {
      remember: true,
      username: parsed.username,
      password: parsed.password,
    };
  } catch {
    return emptyCredentials();
  }
}

export function saveRememberedCredentials(
  storage: StorageLike | null = getStorage(),
  credentials: Pick<RememberedCredentials, 'username' | 'password'>,
): void {
  if (!storage) return;

  storage.setItem(
    REMEMBER_CREDENTIALS_KEY,
    JSON.stringify({
      version: 1,
      remember: true,
      username: credentials.username,
      password: credentials.password,
    }),
  );
}

export function clearRememberedCredentials(storage: StorageLike | null = getStorage()): void {
  storage?.removeItem(REMEMBER_CREDENTIALS_KEY);
}
