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
// slot content is exactly the old hard-coded button). `align` (same date)
// lets a left-anchored trigger (the avatar, at the right end of the
// topbar) open its menu without running off the edge of the screen —
// RosterListView's ⋮ (always near the right edge of its own row) keeps
// the default.
const props = defineProps({
  items: { type: Array, required: true }, // [{ key, label, disabled? }]
  align: { type: String, default: 'right' }, // 'right' | 'left'
})
const emit = defineEmits(['select'])

const open = ref(false)
const root = ref(null)

function toggle() {
  open.value = !open.value
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
onBeforeUnmount(() => document.removeEventListener('click', onClickOutside))
</script>

<template>
  <div ref="root" class="actions-menu" @click.stop>
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
