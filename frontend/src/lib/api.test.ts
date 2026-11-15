import { describe, expect, it } from 'vitest'
import { resolverApiBase } from './api'

describe('resolverApiBase (build-time API URL)', () => {
  it('falls back to the local API when the value is undefined', () => {
    expect(resolverApiBase(undefined)).toBe('http://localhost:8000')
  })

  it('falls back to the local API when the value is an empty string', () => {
    // Docker sets the variable from an empty build argument, so the bundle can
    // carry "" and every request would go to the static site instead of the API.
    expect(resolverApiBase('')).toBe('http://localhost:8000')
  })

  it('falls back to the local API when the value is only whitespace', () => {
    expect(resolverApiBase('   ')).toBe('http://localhost:8000')
  })

  it('keeps a configured URL', () => {
    expect(resolverApiBase('https://radar-api.example.test')).toBe('https://radar-api.example.test')
  })

  it('removes trailing slashes so paths are not doubled', () => {
    expect(resolverApiBase('https://radar-api.example.test/')).toBe(
      'https://radar-api.example.test',
    )
  })
})
