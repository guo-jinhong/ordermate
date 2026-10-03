import { computed, watch } from 'vue'

import { useChatStore } from '../stores/chat'

type Announce = (message: string) => Promise<void>

export function useChatAnnouncements(announce: Announce): void {
  const chat = useChatStore()
  const state = computed(() => {
    const assistant = chat.latestAssistant
    if (!assistant) return null
    return {
      id: assistant.id,
      streamPhase: assistant.streamPhase,
      statusText: assistant.status?.text ?? null,
      confirmationToken: assistant.confirmation?.token ?? null,
      confirmationDescription: assistant.confirmation?.description ?? null,
      confirmationPhase: assistant.confirmationPhase,
      confirmationMessage: assistant.confirmationResult?.message ?? null,
    }
  })

  watch(state, (current, previous) => {
    if (!current) return

    const isNewConfirmation = current.confirmationToken != null
      && current.confirmationPhase === 'pending'
      && current.confirmationToken !== previous?.confirmationToken
    if (isNewConfirmation) {
      void announce(`需要确认：${current.confirmationDescription ?? '请检查操作内容。'}`)
      return
    }

    const confirmationChanged = current.confirmationToken != null
      && current.confirmationPhase !== previous?.confirmationPhase
    if (confirmationChanged && current.confirmationPhase === 'executed') {
      void announce(`操作已完成：${current.confirmationMessage ?? '已为您完成这次操作。'}`)
      return
    }
    if (confirmationChanged && current.confirmationPhase === 'cancelled') {
      void announce(`本次未操作：${current.confirmationMessage ?? '购物车和订单保持不变。'}`)
      return
    }
    if (confirmationChanged && current.confirmationPhase === 'failed') {
      void announce(`操作未完成：${current.confirmationMessage ?? '请重新发起操作。'}`)
      return
    }

    if (current.streamPhase === previous?.streamPhase) return
    if (current.streamPhase === 'done' && current.confirmationToken == null) {
      void announce('回复已完成。')
    } else if (current.streamPhase === 'cancelled') {
      void announce('回答已停止。')
    } else if (current.streamPhase === 'error') {
      void announce(current.statusText ?? '回复生成失败。')
    }
  })
}
