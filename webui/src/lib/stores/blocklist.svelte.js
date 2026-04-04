import { writable } from 'svelte/store';

import { createRule, deleteRule, getBlocklist, updateRule } from '$lib/api/blocklist';
import { toast } from '$lib/stores/toast.svelte';

const initial = {
  rules: [],
  loading: false,
  error: null
};

const { subscribe, update } = writable(initial);

function makeIdempotencyKey() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

async function loadRules() {
  update((state) => ({ ...state, loading: true, error: null }));
  try {
    const data = await getBlocklist();
    update((state) => ({ ...state, rules: data.rules ?? [], loading: false, error: null }));
  } catch (error) {
    update((state) => ({ ...state, loading: false, error: error instanceof Error ? error.message : 'Failed to load blocklist' }));
  }
}

function hydrate(rules = []) {
  update((state) => ({ ...state, rules, error: null }));
}

async function createRuleAction(payload) {
  const tempId = Date.now() * -1;
  const optimistic = {
    id: tempId,
    pattern: payload.pattern,
    rule_type: payload.rule_type,
    reason: payload.reason ?? null,
    enabled: payload.enabled ?? true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  };

  let snapshot = null;
  update((state) => {
    snapshot = state;
    return { ...state, rules: [...state.rules, optimistic], error: null };
  });

  try {
    const created = await createRule(payload, makeIdempotencyKey());
    update((state) => ({
      ...state,
      rules: state.rules.map((rule) => (rule.id === tempId ? created : rule)),
      error: null
    }));
  } catch (error) {
    if (snapshot) {
      update(() => snapshot);
    }
    const message = error instanceof Error ? error.message : 'Failed to create block rule';
    update((state) => ({ ...state, error: message }));
    toast.push(message, 'error');
    throw error;
  }
}

async function updateRuleAction(id, payload) {
  let snapshot = null;
  update((state) => {
    snapshot = state;
    return {
      ...state,
      rules: state.rules.map((rule) => (rule.id === id ? { ...rule, ...payload } : rule)),
      error: null
    };
  });

  try {
    const updated = await updateRule(id, payload, makeIdempotencyKey());
    update((state) => ({
      ...state,
      rules: state.rules.map((rule) => (rule.id === id ? updated : rule)),
      error: null
    }));
  } catch (error) {
    if (snapshot) {
      update(() => snapshot);
    }
    const message = error instanceof Error ? error.message : 'Failed to update block rule';
    update((state) => ({ ...state, error: message }));
    toast.push(message, 'error');
    throw error;
  }
}

async function deleteRuleAction(id) {
  let snapshot = null;
  update((state) => {
    snapshot = state;
    return {
      ...state,
      rules: state.rules.filter((rule) => rule.id !== id),
      error: null
    };
  });

  try {
    await deleteRule(id, makeIdempotencyKey());
  } catch (error) {
    if (snapshot) {
      update(() => snapshot);
    }
    const message = error instanceof Error ? error.message : 'Failed to delete block rule';
    update((state) => ({ ...state, error: message }));
    toast.push(message, 'error');
    throw error;
  }
}

export const blocklist = {
  subscribe,
  loadRules,
  hydrate,
  createRule: createRuleAction,
  updateRule: updateRuleAction,
  deleteRule: deleteRuleAction
};
