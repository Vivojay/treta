import { describe, expect, it } from 'vitest';

import { apiHeaders, createApi, statusLabel } from './api';

describe('fleet presentation semantics', () => {
  it('uses labels in addition to raw status values', () => {
    expect(statusLabel('RETURNING_HOME')).toBe('Returning Home');
    expect(statusLabel('CRITICAL')).toBe('Critical');
  });

  it('scopes local identity to the synthetic tenant without a secret', () => {
    expect(apiHeaders('viewer')).toEqual({
      'Content-Type': 'application/json',
      'X-Treta-Actor': 'local-viewer',
      'X-Treta-Role': 'viewer',
      'X-Treta-Tenant-ID': 'tenant-synthetic'
    });
  });

  it('adds a different idempotency key to consecutive mutations', async () => {
    const calls: RequestInit[] = [];
    globalThis.fetch = async (_input, init) => {
      calls.push(init ?? {});
      return new Response('{}', {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      });
    };
    const api = createApi('http://synthetic.invalid');
    await api.request('/one', 'operator', 'POST', {});
    await api.request('/two', 'operator', 'POST', {});
    expect(
      (calls[0].headers as Record<string, string>)['Idempotency-Key']
    ).toBe('ui-1');
    expect(
      (calls[1].headers as Record<string, string>)['Idempotency-Key']
    ).toBe('ui-2');
  });

  it('surfaces an explicit API error', async () => {
    globalThis.fetch = async () =>
      new Response(JSON.stringify({ error: { detail: 'role denied' } }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' }
      });
    await expect(
      createApi('').request('/denied', 'viewer', 'POST')
    ).rejects.toThrow('role denied');
  });

  it('uses the HTTP status text when an error body has no detail', async () => {
    globalThis.fetch = async () =>
      new Response('{}', {
        status: 503,
        statusText: 'Service Unavailable',
        headers: { 'Content-Type': 'application/json' }
      });
    await expect(createApi('').request('/offline', 'viewer')).rejects.toThrow(
      'Service Unavailable'
    );
  });
});
