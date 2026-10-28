// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import { createApp, nextTick, type App } from 'vue';
import { createPinia, setActivePinia } from 'pinia';
import ModelCenter from './ModelCenter.vue';
import { useModelStore } from '@/stores/models';
import type { ModelControlPlane, ModelProfile } from '@/types/models';

describe('Model thinking mode', () => {
  let app: App<Element> | null = null;
  let root: HTMLDivElement | null = null;

  afterEach(() => {
    app?.unmount();
    root?.remove();
    vi.restoreAllMocks();
    app = null;
    root = null;
  });

  it.each([null, false, true])(
    'loads and submits thinking mode %s without coercing it',
    async (mode) => {
      const pinia = createPinia();
      setActivePinia(pinia);
      const store = useModelStore();
      const profile: ModelProfile = {
        id: 'model_' + 'a'.repeat(32),
        display_name: 'Test',
        provider: 'openai',
        model_name: 'qwen',
        base_url: '',
        timeout_seconds: 120,
        enable_thinking: mode,
        supports_stream: true,
        supports_structured_output: true,
        enabled: true,
        source: 'user',
        version: 1,
        created_at: '',
        updated_at: '',
      };
      const plane: ModelControlPlane = {
        schema_version: 1,
        catalog_hash: 'a'.repeat(64),
        api_key_configured: true,
        profiles: [profile],
        assignments: { answer: profile, fast: profile, grader: profile, evaluator: profile },
        requirements: Object.fromEntries(
          ['answer', 'fast', 'grader', 'evaluator'].map((role) => [
            role,
            {
              supports_stream: role === 'answer',
              supports_structured_output: role !== 'answer',
              temperature: 0,
            },
          ])
        ) as ModelControlPlane['requirements'],
      };
      store.controlPlane = plane;
      vi.spyOn(store, 'fetchControlPlane').mockResolvedValue(plane);
      const save = vi.spyOn(store, 'updateProfile').mockResolvedValue(plane);
      root = document.createElement('div');
      document.body.append(root);
      app = createApp(ModelCenter);
      app.use(pinia);
      app.mount(root);
      await nextTick();
      const edit = root.querySelector<HTMLButtonElement>('button[aria-label*="编辑"]');
      expect(edit).not.toBeNull();
      edit!.click();
      await nextTick();
      const form = document.querySelector<HTMLFormElement>('form');
      expect(form).not.toBeNull();
      const label = Array.from(form!.querySelectorAll('label')).find((item) =>
        item.textContent?.includes('思考模式')
      );
      const select = label!.querySelector('select')!;
      expect(select.selectedIndex).toBe(mode === null ? 0 : mode === false ? 1 : 2);
      const nextMode = mode === null ? false : mode === false ? true : null;
      select.selectedIndex = nextMode === null ? 0 : nextMode === false ? 1 : 2;
      select.dispatchEvent(new Event('change', { bubbles: true }));
      await nextTick();
      form!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
      await nextTick();
      expect(save).toHaveBeenCalledWith(
        profile.id,
        expect.objectContaining({ enable_thinking: nextMode })
      );
    }
  );
});
