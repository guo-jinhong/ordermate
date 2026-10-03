<script setup lang="ts">
import { useChatStore } from '../../stores/chat'
import { useSessionStore } from '../../stores/session'
import { useViewStore } from '../../stores/view'
import type { PromptAction } from '../../types/chat'
import ComposerBox from './ComposerBox.vue'
import MessageList from './MessageList.vue'
import WelcomeState from './WelcomeState.vue'

const chat = useChatStore()
const session = useSessionStore()
const view = useViewStore()

const handlePrompt = async (action: PromptAction): Promise<void> => {
  if (action.authRequired && !session.isAuthenticated) {
    session.requestLoginForAction(action.prompt, action.label, action.displayPrompt)
    view.openAccount()
    return
  }
  if (action.preserveScroll) {
    await chat.send(action.prompt, action.displayPrompt, { preserveScroll: true })
  } else if (action.displayPrompt) {
    await chat.send(action.prompt, action.displayPrompt)
  } else {
    await chat.send(action.prompt)
  }
}
</script>

<template>
  <main id="workspace" class="workspace" :data-conversation="chat.hasConversation" tabindex="-1">
    <WelcomeState
      v-if="!chat.hasConversation"
      :authenticated="session.isAuthenticated"
      :login-required="session.chatLoginRequired"
      :busy="!chat.canSend"
      @prompt="handlePrompt"
    />
    <MessageList v-else @prompt="handlePrompt" @confirm="chat.confirm" />
    <ComposerBox />
  </main>
</template>

<style scoped>
.workspace { display: grid; grid-template-rows: minmax(0, 1fr) auto; width: 100%; height: 100%; min-width: 0; min-height: 0; overflow: hidden; background: var(--color-canvas); }
</style>
