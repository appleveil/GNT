<script setup>
import AuthorizerConfirmModal from '@/components/shared/AuthorizerConfirmModal.vue'
import AppToast from '@/components/shared/AppToast.vue'
</script>

<template>
  <router-view />
  <AuthorizerConfirmModal />
  <AppToast />
</template>
