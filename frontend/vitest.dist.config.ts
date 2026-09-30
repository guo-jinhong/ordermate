import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'node',
    include: ['tests/dist-contract.test.ts', 'tests/nginx-contract.test.ts'],
  },
})
