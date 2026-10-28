// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import { createApp, nextTick, type App } from 'vue';
import { createPinia, setActivePinia } from 'pinia';
import CapabilityAdmin from './CapabilityAdmin.vue';
import { useCapabilityAdminStore } from '@/stores/capabilityAdmin';
import type { CapabilityControlPlane } from '@/types/capabilities';

describe('SQL Assistant configuration form', () => {
  let app: App<Element> | null = null;
  let root: HTMLDivElement | null = null;

  afterEach(() => {
    app?.unmount();
    root?.remove();
    vi.restoreAllMocks();
    app = null;
    root = null;
  });

  it.each([
    { timeout: 10, cost: 100000 },
    { timeout: 0.15, cost: 100000.25 },
  ])('submits valid budgets $timeout / $cost with advanced settings collapsed', async (budgets) => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = useCapabilityAdminStore();
    const controlPlane: CapabilityControlPlane = {
      schema_version: 1,
      web_research: { enabled: false, provider: 'tavily-keyless', api_key_required: false },
      skills: [],
      custom_tools: [],
      builtin_tools: [],
      sql_assistant: {
        enabled: true,
        dsn_secret_name: 'SQL_ASSISTANT_DSN',
        dsn_configured: true,
        expected_role: 'supermew_sql_reader',
        allowed_schemas: ['analytics'],
        allowed_tables: ['analytics.orders'],
        sensitive_columns: [],
        statement_timeout_seconds: budgets.timeout,
        max_rows: 200,
        max_result_bytes: 262144,
        max_estimated_cost: budgets.cost,
        max_estimated_rows: 100000,
        max_estimated_bytes: 8388608,
        catalog_cache_ttl_seconds: 300,
        updated_at: '2026-07-21T00:00:00Z',
      },
    };
    store.controlPlane = controlPlane;
    vi.spyOn(store, 'fetchControlPlane').mockResolvedValue(controlPlane);
    const save = vi.spyOn(store, 'updateSqlAssistant').mockResolvedValue(controlPlane);

    root = document.createElement('div');
    document.body.appendChild(root);
    app = createApp(CapabilityAdmin);
    app.use(pinia);
    app.mount(root);
    await nextTick();

    const form = root.querySelector<HTMLFormElement>('.sql-form');
    expect(form).not.toBeNull();
    expect(form?.querySelector('details')?.open).toBe(false);
    expect(form?.checkValidity()).toBe(true);
    form?.querySelector<HTMLButtonElement>('button[type="submit"]')?.click();
    await nextTick();

    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({
        enabled: true,
        statement_timeout_seconds: budgets.timeout,
        max_estimated_cost: budgets.cost,
        allowed_tables: ['analytics.orders'],
      })
    );
    const timeout = form?.querySelector<HTMLInputElement>('input[type="number"]');
    expect(timeout).not.toBeNull();
    timeout!.value = '0';
    expect(form?.checkValidity()).toBe(false);
  });
});
