import { nextTick, shallowRef } from 'vue'

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

export function useFocusRestore() {
  const trigger = shallowRef<HTMLElement | null>(null)

  const rememberTrigger = (): void => {
    trigger.value = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null
  }

  const focusFirst = (container: HTMLElement | null): void => {
    container?.querySelector<HTMLElement>(FOCUSABLE)?.focus()
  }

  const restoreFocus = async (): Promise<void> => {
    const target = trigger.value
    trigger.value = null
    await nextTick()
    if (target?.isConnected) target.focus()
  }

  const trapFocus = (event: KeyboardEvent, container: HTMLElement | null): void => {
    if (event.key !== 'Tab' || !container) return
    const controls = [...container.querySelectorAll<HTMLElement>(FOCUSABLE)]
      .filter((control) => !control.hidden && control.getAttribute('aria-hidden') !== 'true')
    if (!controls.length) return

    const first = controls[0]
    const last = controls.at(-1)
    if (!first || !last) return
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    } else if (!container.contains(document.activeElement)) {
      event.preventDefault()
      first.focus()
    }
  }

  return { rememberTrigger, focusFirst, restoreFocus, trapFocus }
}
