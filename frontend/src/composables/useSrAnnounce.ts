import { nextTick, ref } from 'vue'
import type { Ref } from 'vue'

export interface UseSrAnnounce {
  announcement: Ref<string>
  announce: (message: string) => Promise<void>
}

export function useSrAnnounce(): UseSrAnnounce {
  const announcement = ref('')

  const announce = async (message: string): Promise<void> => {
    announcement.value = ''
    await nextTick()
    announcement.value = message
  }

  return { announcement, announce }
}
