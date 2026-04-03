import { writable } from 'svelte/store';

interface Toast {
  id: string;
  message: string;
  type: 'success' | 'error' | 'warning' | 'info';
  expires: number; // timestamp
}

const { subscribe, set, update } = writable<Toast[]>([]);

function push(message: string, type: 'success' | 'error' | 'warning' | 'info' = 'info', duration = 5000) {
  const id = Math.random().toString(36).substr(2, 9);
  const expires = Date.now() + duration;

  update((toasts) => [
    ...toasts,
    { id, message, type, expires }
  ]);

  // Auto-remove after duration
  setTimeout(() => {
    dismiss(id);
  }, duration);

  return id;
}

function dismiss(id: string) {
  update((toasts) => toasts.filter((t) => t.id !== id));
}

function clear() {
  set([]);
}

export const toast = {
  subscribe,
  push,
  dismiss,
  clear
};
