<script setup lang="ts">
defineProps<{ message: string }>()
</script>

<template>
  <p class="sr-only" role="status" aria-live="polite" aria-atomic="true">{{ message }}</p>
</template>
