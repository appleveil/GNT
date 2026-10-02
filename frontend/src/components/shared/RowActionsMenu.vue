<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

// Generic "⋮" actions menu (2026-09-24) — first used by RosterListView's
// Players table (Deal / Chips limit / View ledger / Payout), written
// generic enough for any other row-action list later. No API calls, no
// navigation of its own: the caller supplies `items` and reacts to
// `select`, same "purely presentational" split LedgerTable.vue already
// established for row rendering.
//
// `trigger` slot (added 2026-10-02) — AppShell.vue's Cashier avatar menu
// reuses this component with its own avatar circle as the trigger instead
// of the default ⋮ button; every other caller is unaffected (the default
// slot content is exactly the old hard-coded button). `align` picks which
// edge of the trigger the menu lines up with: 'right' (default) grows the
// menu leftward, which is what a trigger near the right edge of the page
// needs; 'left' grows it rightward.
//
// `openOn: 'hover'` also opens the menu on mouse hover or keyboard focus
// and closes it shortly after the pointer/focus leaves. Tap/click still
// toggles, for touch screens with no hover. A tap fires focus (and, on
// some browsers, emulated hover) just before its click, so a click that
// lands within OPEN_GRACE_MS of a hover/focus open leaves the menu open
// instead of toggling it straight back shut.
const props = defineProps({
  items: { type: Array, required: true }, // [{ key, label, disabled? }]
  align: { type: String, default: 'right' }, // 'right' | 'left'
  openOn: { type: String, default: 'click' }, // 'click' | 'hover'
})
const emit = defineEmits(['select'])

const OPEN_GRACE_MS = 400
const CLOSE_DELAY_MS = 150

const open = ref(false)
const root = ref(null)
let openedAt = 0
let closeTimer = null

function cancelClose() {
  clearTimeout(closeTimer)
  closeTimer = null
}
function openSoft() {
  cancelClose()
  if (!open.value) {
    open.value = true
    openedAt = Date.now()
  }
}
function closeSoon() {
  cancelClose()
  closeTimer = setTimeout(() => { open.value = false }, CLOSE_DELAY_MS)
}

function toggle() {
  cancelClose()
  if (open.value && props.openOn === 'hover' && Date.now() - openedAt < OPEN_GRACE_MS) return
  open.value = !open.value
}
function onPointerEnter(e) {
  if (props.openOn === 'hover' && e.pointerType === 'mouse') openSoft()
}
function onPointerLeave(e) {
  if (props.openOn === 'hover' && e.pointerType === 'mouse') closeSoon()
}
function onFocusIn() {
  if (props.openOn === 'hover') openSoft()
}
function onFocusOut(e) {
  if (props.openOn === 'hover' && !root.value?.contains(e.relatedTarget)) closeSoon()
}
function onSelect(item) {
  if (item.disabled) return
  open.value = false
  emit('select', item.key)
}
function onClickOutside(e) {
  if (open.value && root.value && !root.value.contains(e.target)) open.value = false
}
onMounted(() => document.addEventListener('click', onClickOutside))
onBeforeUnmount(() => {
  document.removeEventListener('click', onClickOutside)
  cancelClose()
})
</script>

<template>
  <div
    ref="root" class="actions-menu" @click.stop
    @pointerenter="onPointerEnter" @pointerleave="onPointerLeave" @focusin="onFocusIn" @focusout="onFocusOut"
  >
    <slot name="trigger" :toggle="toggle" :open="open">
      <button class="dots-btn" type="button" aria-label="Row actions" @click="toggle">&#8942;</button>
    </slot>
    <div v-if="open" class="menu-pop" :class="{ 'menu-pop--left': align === 'left' }">
      <button
        v-for="item in items" :key="item.key" type="button" class="menu-item"
        :class="{ 'menu-item--disabled': item.disabled }" :disabled="item.disabled"
        @click="onSelect(item)"
      >{{ item.label }}</button>
    </div>
  </div>
</template>

<style scoped>
.actions-menu { position: relative; display: inline-block; }
.dots-btn {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-tertiary);
  font-size: 17px;
  line-height: 1;
  cursor: pointer;
}
.dots-btn:hover { background: var(--bg); color: var(--text-primary); }

.menu-pop {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  min-width: 160px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-md);
  padding: 4px;
  z-index: 20;
  display: flex;
  flex-direction: column;
}
.menu-pop--left { right: auto; left: 0; }
.menu-item {
  border: none;
  background: none;
  text-align: left;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  cursor: pointer;
}
.menu-item:hover { background: var(--bg); }
.menu-item--disabled { color: var(--text-tertiary); cursor: not-allowed; }
.menu-item--disabled:hover { background: none; }
</style>
