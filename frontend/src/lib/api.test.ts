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

  it('prefers the runtime value injected by the container', () => {
    expect(resolverApiBase('https://build.example.test', 'https://runtime.example.test')).toBe(
      'https://runtime.example.test',
    )
  })

  it('falls back to the build-time value when the runtime one is empty', () => {
    expect(resolverApiBase('https://build.example.test', '')).toBe('https://build.example.test')
    expect(resolverApiBase('https://build.example.test', '   ')).toBe('https://build.example.test')
  })

  it('ignores trailing slashes on the runtime value too', () => {
    expect(resolverApiBase(undefined, 'https://runtime.example.test/')).toBe(
      'https://runtime.example.test',
    )
  })
})
